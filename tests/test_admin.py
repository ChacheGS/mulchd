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


async def test_create_user_duplicate_does_not_log(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory

    await admin_client.post("/admin/users", data={"username": "jorge", "display_name": "Jorge"})
    resp = await admin_client.post(
        "/admin/users",
        data={"username": "jorge", "display_name": "Jorge 2"},
        follow_redirects=False,
    )
    assert resp.status_code == 409

    count = await InstanceEvent.filter(category=InstanceEventCategory.USER_CREATED).count()
    assert count == 1


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


async def test_deactivate_blocked_for_last_admin_does_not_log(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory, User

    admin_user = await User.filter(username="admin").first()

    resp = await admin_client.post(
        f"/admin/users/{admin_user.id}/deactivate", follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/admin/users/{admin_user.id}?error=last_admin"

    count = await InstanceEvent.filter(category=InstanceEventCategory.USER_DEACTIVATED).count()
    assert count == 0


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


async def test_project_detail_shows_invite_creator(admin_client):
    from mulchd.models import Organization, Project

    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    await admin_client.post(
        f"/admin/projects/{project.id}/invites",
        data={"role": "writer", "max_uses": "", "expires_in": "", "allowed_email_domains": ""},
    )

    resp = await admin_client.get(f"/admin/projects/{project.id}")
    assert resp.status_code == 200
    assert "by admin" in resp.text


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


async def test_add_membership_logs_event(admin_client):
    from mulchd.auth import create_user
    from mulchd.models import InstanceEvent, InstanceEventCategory, Organization, Project

    target, _ = await create_user("memberadd", "Member Add")
    org = await Organization.create(slug="acme", display_name="Acme")
    project = await Project.create(slug="infra", display_name="Infra", org=org)

    resp = await admin_client.post(
        "/admin/memberships",
        data={"user_id": target.id, "project_id": project.id, "role": "writer"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    event = await InstanceEvent.get(category=InstanceEventCategory.MEMBERSHIP_ADDED)
    assert event.subject_user_id == target.id
    assert event.project_id == project.id
    assert event.detail == {"role": "writer"}


async def test_remove_membership_logs_event(admin_client):
    from mulchd.auth import create_user
    from mulchd.models import (
        InstanceEvent,
        InstanceEventCategory,
        Organization,
        Project,
        Role,
        UserMembership,
    )

    target, _ = await create_user("memberremove", "Member Remove")
    org = await Organization.create(slug="acme2", display_name="Acme2")
    project = await Project.create(slug="infra2", display_name="Infra2", org=org)
    membership = await UserMembership.create(user=target, project=project, role=Role.WRITER)

    resp = await admin_client.post(
        f"/admin/memberships/{membership.id}/remove", follow_redirects=False
    )
    assert resp.status_code == 303

    event = await InstanceEvent.get(category=InstanceEventCategory.MEMBERSHIP_REMOVED)
    assert event.subject_user_id == target.id
    assert event.project_id == project.id


async def test_duplicate_membership_does_not_log(admin_client):
    from mulchd.auth import create_user
    from mulchd.models import InstanceEvent, InstanceEventCategory, Organization, Project

    target, _ = await create_user("memberdup", "Member Dup")
    org = await Organization.create(slug="acmedup", display_name="AcmeDup")
    project = await Project.create(slug="infradup", display_name="InfraDup", org=org)

    await admin_client.post(
        "/admin/memberships",
        data={"user_id": target.id, "project_id": project.id, "role": "writer"},
    )
    resp = await admin_client.post(
        "/admin/memberships",
        data={"user_id": target.id, "project_id": project.id, "role": "writer"},
        follow_redirects=False,
    )
    assert resp.status_code == 409

    count = await InstanceEvent.filter(category=InstanceEventCategory.MEMBERSHIP_ADDED).count()
    assert count == 1


async def test_remove_nonexistent_membership_does_not_log(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory

    resp = await admin_client.post("/admin/memberships/999999/remove", follow_redirects=False)
    assert resp.status_code == 303

    count = await InstanceEvent.filter(category=InstanceEventCategory.MEMBERSHIP_REMOVED).count()
    assert count == 0


async def test_create_user_logs_event(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory, User

    resp = await admin_client.post(
        "/admin/users",
        data={"username": "loguser", "display_name": "Log User"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    new_user = await User.get(username="loguser")
    event = await InstanceEvent.get(category=InstanceEventCategory.USER_CREATED)
    assert event.subject_user_id == new_user.id


async def test_deactivate_user_logs_event(admin_client):
    from mulchd.auth import create_user
    from mulchd.models import InstanceEvent, InstanceEventCategory

    target, _ = await create_user("logdeactivate", "Log Deactivate")

    resp = await admin_client.post(
        f"/admin/users/{target.id}/deactivate", follow_redirects=False
    )
    assert resp.status_code == 303

    event = await InstanceEvent.get(category=InstanceEventCategory.USER_DEACTIVATED)
    assert event.subject_user_id == target.id


async def test_reset_token_logs_event(admin_client):
    from mulchd.auth import create_user
    from mulchd.models import InstanceEvent, InstanceEventCategory

    target, _ = await create_user("logreset", "Log Reset")

    resp = await admin_client.post(
        f"/admin/users/{target.id}/reset-token", follow_redirects=False
    )
    assert resp.status_code == 303

    event = await InstanceEvent.get(category=InstanceEventCategory.TOKEN_RESET)
    assert event.subject_user_id == target.id


async def test_create_org_logs_event(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory

    resp = await admin_client.post(
        "/admin/orgs",
        data={"slug": "logorg", "display_name": "Log Org"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    event = await InstanceEvent.get(category=InstanceEventCategory.ORG_CREATED)
    assert event.detail == {"org_slug": "logorg"}


async def test_create_project_logs_event(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory, Organization

    org = await Organization.create(slug="logprojorg", display_name="Log Proj Org")
    resp = await admin_client.post(
        "/admin/projects",
        data={"org_id": org.id, "slug": "logproj", "display_name": "Log Proj"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    event = await InstanceEvent.get(category=InstanceEventCategory.PROJECT_CREATED)
    assert event.project_id is not None


async def test_create_invite_logs_event(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory, Organization, Project

    org = await Organization.create(slug="loginviteorg", display_name="Log Invite Org")
    project = await Project.create(slug="loginviteproj", display_name="Log Invite Proj", org=org)
    resp = await admin_client.post(
        f"/admin/projects/{project.id}/invites",
        data={"role": "writer", "max_uses": "", "expires_in": "", "allowed_email_domains": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    event = await InstanceEvent.get(category=InstanceEventCategory.INVITE_CREATED)
    assert event.project_id == project.id
    assert event.detail == {"role": "writer"}


async def test_revoke_invite_logs_event(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory, InviteLink, Organization, Project

    org = await Organization.create(slug="logrevokeorg", display_name="Log Revoke Org")
    project = await Project.create(slug="logrevokeproj", display_name="Log Revoke Proj", org=org)
    invite = await InviteLink.create(token="logrevoketoken", project=project, role="writer")

    resp = await admin_client.post(
        f"/admin/invites/{invite.id}/revoke", follow_redirects=False
    )
    assert resp.status_code == 303

    event = await InstanceEvent.get(category=InstanceEventCategory.INVITE_REVOKED)
    assert event.project_id == project.id


async def test_create_org_duplicate_does_not_log(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory

    await admin_client.post("/admin/orgs", data={"slug": "duporg", "display_name": "Dup Org"})
    resp = await admin_client.post(
        "/admin/orgs",
        data={"slug": "duporg", "display_name": "Dup Org 2"},
        follow_redirects=False,
    )
    assert resp.status_code == 409

    count = await InstanceEvent.filter(category=InstanceEventCategory.ORG_CREATED).count()
    assert count == 1


async def test_create_project_duplicate_does_not_log(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory, Organization

    org = await Organization.create(slug="dupprojorg", display_name="Dup Proj Org")
    await admin_client.post(
        "/admin/projects",
        data={"org_id": org.id, "slug": "dupproj", "display_name": "Dup Proj"},
    )
    resp = await admin_client.post(
        "/admin/projects",
        data={"org_id": org.id, "slug": "dupproj", "display_name": "Dup Proj 2"},
        follow_redirects=False,
    )
    assert resp.status_code == 409

    count = await InstanceEvent.filter(category=InstanceEventCategory.PROJECT_CREATED).count()
    assert count == 1


async def test_activity_page_renders(admin_client):
    resp = await admin_client.get("/admin/activity")
    assert resp.status_code == 200
    assert "Activity" in resp.text


async def test_activity_page_shows_events(admin_client):
    from mulchd.instance_events import log_event
    from mulchd.models import InstanceEventCategory, Organization, Project, User

    admin = await User.filter(username="admin").first()
    org = await Organization.create(slug="activityorg", display_name="Activity Org")
    project = await Project.create(slug="activityproj", display_name="Activity Proj", org=org)
    await log_event(
        InstanceEventCategory.PROJECT_CREATED, actor=admin, project=project
    )

    resp = await admin_client.get("/admin/activity")
    assert resp.status_code == 200
    assert "Created project activityorg/activityproj" in resp.text


async def test_activity_page_filters_by_category(admin_client):
    from mulchd.instance_events import log_event
    from mulchd.models import InstanceEventCategory, Organization, User

    admin = await User.filter(username="admin").first()
    await log_event(InstanceEventCategory.ORG_CREATED, actor=admin, detail={"org_slug": "x"})
    org = await Organization.create(slug="filtertest", display_name="Filter Test")

    resp = await admin_client.get(
        f"/admin/activity?category={InstanceEventCategory.ORG_CREATED.value}"
    )
    assert resp.status_code == 200
    assert "Created org x" in resp.text
