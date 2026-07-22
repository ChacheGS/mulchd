import pytest


async def test_dashboard_requires_auth(client):
    resp = await client.get("/admin/", follow_redirects=False)
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


async def test_dashboard_rejects_non_admin_user(client):
    from mulchd.auth import create_user
    from mulchd.connect import _signer

    user, _ = await create_user("regular", "Regular User")
    signed = _signer().dumps(user.id)
    resp = await client.get(
        "/admin/", cookies={"mulchd_connect": signed}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


async def test_dashboard_renders(admin_client):
    resp = await admin_client.get("/admin/")
    assert resp.status_code == 200
    assert "Dashboard" in resp.text


async def test_create_user(admin_client):
    resp = await admin_client.post(
        "/admin/users",
        data={"username": "jorge", "display_name": "Jorge M."},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/users/created"


async def test_create_user_duplicate(admin_client):
    await admin_client.post("/admin/users", data={"username": "jorge", "display_name": "Jorge"})
    resp = await admin_client.post(
        "/admin/users",
        data={"username": "jorge", "display_name": "Jorge 2"},
        follow_redirects=False,
    )
    assert resp.status_code == 409
    assert "already taken" in resp.text


async def test_token_reveal_page(admin_client):
    await admin_client.post("/admin/users", data={"username": "jorge", "display_name": "Jorge M."})
    resp = await admin_client.get("/admin/users/created")
    assert resp.status_code == 200
    assert "jorge" in resp.text
    assert "/connect" in resp.text  # setup guide URL shown on token reveal page


async def test_token_reveal_clears_on_revisit(admin_client):
    await admin_client.post("/admin/users", data={"username": "jorge", "display_name": "Jorge M."})
    await admin_client.get("/admin/users/created")
    resp = await admin_client.get("/admin/users/created", follow_redirects=False)
    assert resp.status_code == 303


async def test_create_org(admin_client):
    resp = await admin_client.post(
        "/admin/orgs", data={"slug": "acme", "display_name": "Acme Corp"}, follow_redirects=False
    )
    assert resp.status_code == 303


async def test_create_project(admin_client):
    await admin_client.post("/admin/orgs", data={"slug": "acme", "display_name": "Acme"})
    resp = await admin_client.get("/admin/orgs")
    from mulchd.models import Organization

    org = await Organization.get(slug="acme")
    resp = await admin_client.post(
        "/admin/projects",
        data={"org_id": org.id, "slug": "data-platform", "display_name": "Data Platform"},
        follow_redirects=False,
    )
    assert resp.status_code == 303


async def test_add_membership(admin_client):
    await admin_client.post("/admin/orgs", data={"slug": "acme", "display_name": "Acme"})
    from mulchd.models import Organization

    org = await Organization.get(slug="acme")
    await admin_client.post(
        "/admin/projects",
        data={"org_id": org.id, "slug": "proj", "display_name": "Proj"},
    )
    await admin_client.post("/admin/users", data={"username": "jorge", "display_name": "Jorge M."})

    from mulchd.models import Project, User

    user = await User.get(username="jorge")
    project = await Project.get(slug="proj")

    resp = await admin_client.post(
        "/admin/memberships",
        data={"user_id": user.id, "project_id": project.id, "role": "writer"},
        follow_redirects=False,
    )
    assert resp.status_code == 303


async def test_deactivate_user(admin_client):
    await admin_client.post("/admin/users", data={"username": "jorge", "display_name": "Jorge M."})
    from mulchd.models import User

    user = await User.get(username="jorge")
    resp = await admin_client.post(f"/admin/users/{user.id}/deactivate", follow_redirects=False)
    assert resp.status_code == 303
    await user.refresh_from_db()
    assert not user.active


async def test_deactivate_blocked_for_last_admin(admin_client):
    from mulchd.models import User

    admin_user = await User.filter(username="admin").first()

    resp = await admin_client.post(
        f"/admin/users/{admin_user.id}/deactivate", follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/admin/users/{admin_user.id}?error=last_admin"
    await admin_user.refresh_from_db()
    assert admin_user.active is True


async def test_deactivate_allowed_when_other_admin_exists(admin_client):
    from mulchd.admin_grants import grant_superadmin
    from mulchd.auth import create_user
    from mulchd.models import User

    admin_user = await User.filter(username="admin").first()
    other, _ = await create_user("secondadmin", "Second Admin")
    await grant_superadmin(other, granted_by=admin_user)

    resp = await admin_client.post(
        f"/admin/users/{admin_user.id}/deactivate", follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/users"
    await admin_user.refresh_from_db()
    assert admin_user.active is False


async def test_users_page_renders(admin_client):
    resp = await admin_client.get("/admin/users")
    assert resp.status_code == 200
    assert "Add user" in resp.text


async def test_records_count_requires_auth(client, tmp_path, monkeypatch):
    from mulchd.config import settings

    monkeypatch.setattr(settings, "data_path", tmp_path)
    resp = await client.get("/admin/records/count?project=acme/demo", follow_redirects=False)
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


async def test_records_count_no_project(admin_client, tmp_path, monkeypatch):
    from mulchd.config import settings

    monkeypatch.setattr(settings, "data_path", tmp_path)
    resp = await admin_client.get("/admin/records/count")
    assert resp.status_code == 200
    assert resp.json() == {"count": 0}


async def test_records_count_with_jsonl(admin_client, tmp_path, monkeypatch):
    from mulchd.config import settings

    monkeypatch.setattr(settings, "data_path", tmp_path)
    expertise = tmp_path / "acme" / "demo" / ".mulch" / "expertise"
    expertise.mkdir(parents=True)
    (expertise / "architecture.jsonl").write_text(
        '{"id":"mx-aaa","type":"decision"}\n{"id":"mx-bbb","type":"convention"}\n'
    )
    (expertise / "ops.jsonl").write_text('{"id":"mx-ccc","type":"guide"}\n')
    resp = await admin_client.get("/admin/records/count?project=acme/demo")
    assert resp.status_code == 200
    assert resp.json() == {"count": 3}


async def test_audit_page_renders(admin_client):
    resp = await admin_client.get("/admin/audit")
    assert resp.status_code == 200
    assert "Audit" in resp.text


async def test_audit_page_redirects_when_not_logged_in(client):
    resp = await client.get("/admin/audit", follow_redirects=False)
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


async def test_admin_create_user_with_email(admin_client):
    resp = await admin_client.post(
        "/admin/users",
        data={"username": "withmail", "display_name": "With Mail", "email": "wm@example.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    from mulchd.models import User
    user = await User.filter(username="withmail").first()
    assert user is not None
    assert user.email == "wm@example.com"


async def test_admin_user_detail_page(admin_client):
    from mulchd.auth import create_user
    user, _ = await create_user("detailuser", "Detail User", email="d@example.com")
    resp = await admin_client.get(f"/admin/users/{user.id}")
    assert resp.status_code == 200
    assert "detailuser" in resp.text
    assert "Linked identities" in resp.text


async def test_project_detail_page_renders(admin_client):
    from mulchd.models import Organization, Project
    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    resp = await admin_client.get(f"/admin/projects/{project.id}")
    assert resp.status_code == 200
    assert project.display_name in resp.text


async def test_project_detail_renders_invite_rows(admin_client):
    from datetime import UTC, datetime, timedelta

    from mulchd.models import (
        InviteLink,
        InviteUse,
        Organization,
        Project,
        Role,
        User,
    )

    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    user = await User.create(username="bob", display_name="Bob", token_hash="x")
    active = await InviteLink.create(token="t1", project=project, role=Role.ADMIN, max_uses=3, use_count=1)
    await InviteLink.create(
        token="t2", project=project, role=Role.READER,
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    await InviteLink.create(token="t3", project=project, role=Role.WRITER, max_uses=2, use_count=2)
    await InviteLink.create(token="t4", project=project, role=Role.READER, revoked=True)
    await InviteUse.create(invite=active, user=user)

    resp = await admin_client.get(f"/admin/projects/{project.id}")
    assert resp.status_code == 200
    assert "badge-admin" in resp.text
    assert "badge-writer" in resp.text
    assert "expired" in resp.text
    assert "exhausted" in resp.text
    assert "revoked" in resp.text
    assert "bob" in resp.text


async def test_admin_unlink_identity(admin_client):
    from mulchd.auth import create_user
    from mulchd.models import OAuthIdentity
    user, _ = await create_user("unlinkme", "Unlink Me")
    identity = await OAuthIdentity.create(user=user, provider="github", sub="777")
    resp = await admin_client.post(
        f"/admin/users/{user.id}/identities/{identity.id}/unlink",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert not await OAuthIdentity.filter(id=identity.id).exists()


async def test_create_invite_link(admin_client):
    from mulchd.models import InviteLink, Organization, Project, User
    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    resp = await admin_client.post(
        f"/admin/projects/{project.id}/invites",
        data={"role": "writer", "max_uses": "5", "expires_in": "3600", "allowed_email_domains": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    invite = await InviteLink.get(project=project)
    assert resp.headers["location"] == f"/admin/projects/{project.id}?new_token={invite.token}"
    assert invite.role == "writer"
    assert invite.max_uses == 5
    assert invite.expires_at is not None
    admin_user = await User.filter(username="admin").first()
    assert invite.created_by_id == admin_user.id


async def test_grant_admin_access(admin_client):
    from mulchd.admin_grants import is_superadmin
    from mulchd.auth import create_user

    target, _ = await create_user("newadmin", "New Admin")
    resp = await admin_client.post(
        f"/admin/users/{target.id}/grant-admin", follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/admin/users/{target.id}"
    assert await is_superadmin(target) is True


async def test_revoke_admin_access(admin_client):
    from mulchd.admin_grants import grant_superadmin, is_superadmin
    from mulchd.auth import create_user
    from mulchd.models import User

    target, _ = await create_user("removable", "Removable Admin")
    admin_user = await User.filter(username="admin").first()
    await grant_superadmin(target, granted_by=admin_user)

    resp = await admin_client.post(
        f"/admin/users/{target.id}/revoke-admin", follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/admin/users/{target.id}"
    assert await is_superadmin(target) is False


async def test_revoke_admin_blocked_as_last_admin(admin_client):
    from mulchd.admin_grants import is_superadmin
    from mulchd.models import User

    admin_user = await User.filter(username="admin").first()

    resp = await admin_client.post(
        f"/admin/users/{admin_user.id}/revoke-admin", follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/admin/users/{admin_user.id}?error=last_admin"
    assert await is_superadmin(admin_user) is True


async def test_admin_can_revoke_own_access_when_others_exist(admin_client):
    from mulchd.admin_grants import grant_superadmin, is_superadmin
    from mulchd.auth import create_user
    from mulchd.models import User

    admin_user = await User.filter(username="admin").first()
    other, _ = await create_user("otheradmin", "Other Admin")
    await grant_superadmin(other, granted_by=admin_user)

    resp = await admin_client.post(
        f"/admin/users/{admin_user.id}/revoke-admin", follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/admin/users/{admin_user.id}"
    assert await is_superadmin(admin_user) is False


async def test_revoke_invite_link(admin_client):
    from mulchd.models import InviteLink, Organization, Project
    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    invite = await InviteLink.create(
        token="revoketest123",
        project=project,
        role="writer",
    )
    resp = await admin_client.post(f"/admin/invites/{invite.id}/revoke", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/admin/projects/{project.id}"
    await invite.refresh_from_db()
    assert invite.revoked is True


async def test_revoked_admin_loses_access_on_next_request(admin_client):
    from mulchd.admin_grants import grant_superadmin
    from mulchd.auth import create_user
    from mulchd.models import User

    admin_user = await User.filter(username="admin").first()
    other, _ = await create_user("otheradmin2", "Other Admin")
    await grant_superadmin(other, granted_by=admin_user)

    # admin_user revokes their own access (another admin still exists, so this succeeds)
    resp = await admin_client.post(
        f"/admin/users/{admin_user.id}/revoke-admin", follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/admin/users/{admin_user.id}"

    # Same session cookie, next request — must now be locked out of /admin entirely
    resp2 = await admin_client.get("/admin/", follow_redirects=False)
    assert resp2.status_code == 303
    assert "/connect" in resp2.headers["location"]
