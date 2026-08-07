import pytest


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

    admin_user = await User.get(username="admin")

    resp = await admin_client.post(
        f"/admin/users/{admin_user.id}/deactivate", follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/admin/users/{admin_user.id}?error=last_admin"
    await admin_user.refresh_from_db()
    assert admin_user.active is True


async def test_deactivate_blocked_for_last_admin_does_not_log(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory, User

    admin_user = await User.get(username="admin")

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

    admin_user = await User.get(username="admin")
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


async def test_admin_create_user_with_email(admin_client):
    resp = await admin_client.post(
        "/admin/users",
        data={"username": "withmail", "display_name": "With Mail", "email": "wm@example.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    from mulchd.models import User

    user = await User.get(username="withmail")
    assert user is not None
    assert user.email == "wm@example.com"


async def test_admin_user_detail_page(admin_client):
    from mulchd.auth import create_user

    user, _ = await create_user("detailuser", "Detail User", email="d@example.com")
    resp = await admin_client.get(f"/admin/users/{user.id}")
    assert resp.status_code == 200
    assert "detailuser" in resp.text
    assert "Linked identities" in resp.text


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


async def test_grant_admin_access(admin_client):
    from mulchd.admin_grants import is_superadmin
    from mulchd.auth import create_user

    target, _ = await create_user("newadmin", "New Admin")
    resp = await admin_client.post(f"/admin/users/{target.id}/grant-admin", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/admin/users/{target.id}"
    assert await is_superadmin(target) is True


async def test_revoke_admin_access(admin_client):
    from mulchd.admin_grants import grant_superadmin, is_superadmin
    from mulchd.auth import create_user
    from mulchd.models import User

    target, _ = await create_user("removable", "Removable Admin")
    admin_user = await User.get(username="admin")
    await grant_superadmin(target, granted_by=admin_user)

    resp = await admin_client.post(f"/admin/users/{target.id}/revoke-admin", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/admin/users/{target.id}"
    assert await is_superadmin(target) is False


async def test_revoke_admin_blocked_as_last_admin(admin_client):
    from mulchd.admin_grants import is_superadmin
    from mulchd.models import User

    admin_user = await User.get(username="admin")

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

    admin_user = await User.get(username="admin")
    other, _ = await create_user("otheradmin", "Other Admin")
    await grant_superadmin(other, granted_by=admin_user)

    resp = await admin_client.post(
        f"/admin/users/{admin_user.id}/revoke-admin", follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/admin/users/{admin_user.id}"
    assert await is_superadmin(admin_user) is False


async def test_revoked_admin_loses_access_on_next_request(admin_client):
    from mulchd.admin_grants import grant_superadmin
    from mulchd.auth import create_user
    from mulchd.models import User

    admin_user = await User.get(username="admin")
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

    resp = await admin_client.post(f"/admin/users/{target.id}/deactivate", follow_redirects=False)
    assert resp.status_code == 303

    event = await InstanceEvent.get(category=InstanceEventCategory.USER_DEACTIVATED)
    assert event.subject_user_id == target.id


async def test_reset_token_logs_event(admin_client):
    from mulchd.auth import create_user
    from mulchd.models import InstanceEvent, InstanceEventCategory

    target, _ = await create_user("logreset", "Log Reset")

    resp = await admin_client.post(f"/admin/users/{target.id}/reset-token", follow_redirects=False)
    assert resp.status_code == 303

    event = await InstanceEvent.get(category=InstanceEventCategory.TOKEN_RESET)
    assert event.subject_user_id == target.id


async def test_user_detail_shows_memberships(admin_client):
    from mulchd.auth import create_user
    from mulchd.models import Organization, Project, Role, UserMembership

    user, _ = await create_user("jorge", "Jorge M.")
    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    await UserMembership.create(user=user, project=project, role=Role.WRITER)

    resp = await admin_client.get(f"/admin/users/{user.id}")
    assert resp.status_code == 200
    assert "acme/infra" in resp.text
    assert "badge-writer" in resp.text


async def test_user_detail_shows_no_memberships_empty_state(admin_client):
    from mulchd.auth import create_user

    user, _ = await create_user("noproj", "No Proj")

    resp = await admin_client.get(f"/admin/users/{user.id}")
    assert resp.status_code == 200
    assert "No memberships yet." in resp.text
