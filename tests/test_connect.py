import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def test_build_snippets_code_contains_env_var():
    from mulchd.connect import build_connect_snippets

    s = build_connect_snippets("https://example.com", "acme", "demo", "tok-abc")
    assert "MULCHD_TOKEN_ACME_DEMO" in s["mcp_json"]
    assert "${MULCHD_TOKEN_ACME_DEMO}" in s["mcp_json"]
    assert "mulchd" in s["mcp_json"]
    assert "https://example.com/mcp" in s["mcp_json"]


def test_build_snippets_settings_local_contains_token():
    from mulchd.connect import build_connect_snippets

    s = build_connect_snippets("https://example.com", "acme", "demo", "tok-abc")
    assert "MULCHD_TOKEN_ACME_DEMO" in s["settings_local"]
    assert "tok-abc" in s["settings_local"]
    assert "enabledMcpServersJson" in s["settings_local"]


def test_build_snippets_desktop_contains_mcp_remote():
    from mulchd.connect import build_connect_snippets

    s = build_connect_snippets("https://example.com", "acme", "demo", "tok-abc")
    assert "mcp-remote" in s["desktop"]
    assert "mulchd-acme-demo" in s["desktop"]
    assert "tok-abc" in s["desktop"]
    assert "MULCHD_TOKEN_ACME_DEMO" in s["desktop"]


def test_build_snippets_hyphens_become_underscores():
    from mulchd.connect import build_connect_snippets

    s = build_connect_snippets("https://x.com", "my-org", "my-project", "t")
    assert "MULCHD_TOKEN_MY_ORG_MY_PROJECT" in s["mcp_json"]
    assert "MULCHD_TOKEN_MY_ORG_MY_PROJECT" in s["settings_local"]
    assert "MULCHD_TOKEN_MY_ORG_MY_PROJECT" in s["desktop"]


from mulchd.auth import create_project_token, create_user  # existing helpers
from mulchd.models import Organization, Project, UserMembership

# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
async def alice_and_project(db):
    """Returns (user, token, org, project) with a membership."""
    user, token = await create_user("alice", "Alice")
    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="demo", display_name="Demo", org=org)
    await UserMembership.create(user=user, project=project)
    return user, token, org, project


async def _authed_client(client, token: str):
    """Log in and return client (cookie set by side effect)."""
    resp = await client.post(
        "/connect", data={"token": token, "remember_me": ""}, follow_redirects=False
    )
    assert resp.status_code == 303
    return client


# ── login ────────────────────────────────────────────────────────────────────


async def test_connect_login_page_renders(client):
    resp = await client.get("/connect")
    assert resp.status_code == 200


async def test_connect_login_wrong_token_returns_401(client):
    resp = await client.post("/connect", data={"token": "bad", "remember_me": ""})
    assert resp.status_code == 401
    assert "Invalid token" in resp.text


async def test_connect_login_sets_cookie_and_redirects(client, alice_and_project):
    user, token, *_ = alice_and_project
    resp = await client.post(
        "/connect", data={"token": token, "remember_me": ""}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/connect/projects"
    assert "mulchd_connect" in resp.cookies


async def test_connect_login_htmx_returns_hx_redirect(client, alice_and_project):
    user, token, *_ = alice_and_project
    resp = await client.post(
        "/connect",
        data={"token": token, "remember_me": ""},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect") == "/connect/projects"


# ── projects ────────────────────────────────────────────────────────────────


async def test_connect_projects_requires_auth(client):
    resp = await client.get("/connect/projects", follow_redirects=False)
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


async def test_connect_projects_lists_memberships(client, alice_and_project):
    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    resp = await client.get("/connect/projects")
    assert resp.status_code == 200
    assert "demo" in resp.text


# ── project page ────────────────────────────────────────────────────────────


async def test_connect_project_page_renders(client, alice_and_project):
    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    resp = await client.get("/connect/projects/acme/demo")
    assert resp.status_code == 200
    assert "project-page" in resp.text


async def test_connect_project_page_nonmember_404(client, alice_and_project):
    user, token, *_ = alice_and_project
    # Create a second org/project that alice is not a member of
    org2 = await Organization.create(slug="other", display_name="Other")
    await Project.create(slug="secret", display_name="Secret", org=org2)
    await _authed_client(client, token)
    resp = await client.get("/connect/projects/other/secret")
    assert resp.status_code == 404


# ── mint ────────────────────────────────────────────────────────────────────


async def test_connect_mint_returns_snippets(client, alice_and_project):
    user, token, *_ = alice_and_project
    await _authed_client(client, token)
    resp = await client.post("/connect/projects/acme/demo/mint", data={"label": "laptop"})
    assert resp.status_code == 200


async def test_connect_mint_creates_token_in_db(client, alice_and_project):
    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    await client.post("/connect/projects/acme/demo/mint", data={"label": "laptop"})
    from mulchd.models import ProjectToken

    count = await ProjectToken.filter(user=user, project=project, active=True).count()
    assert count == 1


# ── revoke ───────────────────────────────────────────────────────────────────


async def test_connect_revoke_token(client, alice_and_project):
    user, token, org, project = alice_and_project
    pt, _ = await create_project_token(user, project, label="old machine")
    await _authed_client(client, token)
    resp = await client.post(f"/connect/projects/acme/demo/revoke/{pt.id}")
    assert resp.status_code == 200
    await pt.refresh_from_db()
    assert pt.active is False


async def test_connect_revoke_wrong_user_404(client, alice_and_project):
    user, token, org, project = alice_and_project
    # Create a second user and their token
    bob, _ = await create_user("bob", "Bob")
    pt, _ = await create_project_token(bob, project, label="bobs laptop")
    await _authed_client(client, token)  # logged in as alice
    resp = await client.post(f"/connect/projects/acme/demo/revoke/{pt.id}")
    assert resp.status_code == 404


# ── logout ───────────────────────────────────────────────────────────────────


async def test_connect_logout_clears_cookie(client, alice_and_project):
    user, token, *_ = alice_and_project
    await _authed_client(client, token)
    resp = await client.get("/connect/logout", follow_redirects=False)
    assert resp.status_code == 303
    # Cookie should be cleared (max_age=0 or deleted)
    assert "mulchd_connect" not in client.cookies or client.cookies["mulchd_connect"] == ""


# ── OAuth routes ─────────────────────────────────────────────────────────────


async def test_oauth_start_unknown_provider_returns_404(client):
    resp = await client.get("/connect/auth/unknown/start", follow_redirects=False)
    assert resp.status_code == 404


async def test_oauth_callback_unknown_provider_returns_404(client):
    resp = await client.get("/connect/auth/unknown/callback?code=x&state=y")
    assert resp.status_code == 404


async def test_connect_entry_page_has_no_sso_buttons_without_config(client):
    """With no OAuth env vars set in tests, entry page must not show SSO buttons."""
    resp = await client.get("/connect")
    assert resp.status_code == 200
    assert "Sign in with" not in resp.text


async def test_resolve_oauth_identity_creates_link_on_email_match(db):
    """First SSO login: if email matches a user, link is created."""
    from mulchd.auth import create_user
    from mulchd.connect import _resolve_oauth_identity
    from mulchd.models import OAuthIdentity

    user, _ = await create_user("ssouser", "SSO User", email="sso@example.com")
    result = await _resolve_oauth_identity("github", "gh-123", "sso@example.com")
    assert result is not None
    assert result.id == user.id
    # Identity should now be linked
    assert await OAuthIdentity.filter(provider="github", sub="gh-123").exists()


async def test_resolve_oauth_identity_returns_none_for_unknown_email(db):
    from mulchd.connect import _resolve_oauth_identity
    result = await _resolve_oauth_identity("github", "gh-999", "nobody@example.com")
    assert result is None


async def test_resolve_oauth_identity_uses_existing_link(db):
    """Second SSO login: existing OAuthIdentity is found directly."""
    from mulchd.auth import create_user
    from mulchd.connect import _resolve_oauth_identity
    from mulchd.models import OAuthIdentity

    user, _ = await create_user("linked", "Linked User")
    await OAuthIdentity.create(user=user, provider="github", sub="gh-456")
    result = await _resolve_oauth_identity("github", "gh-456", "any@email.com")
    assert result is not None
    assert result.id == user.id


async def test_create_user_from_oauth_sets_first_login_and_logs_event(db):
    from mulchd.auth import create_user_from_oauth
    from mulchd.models import InstanceEvent, InstanceEventCategory

    user = await create_user_from_oauth("github", "gh-1", "new@company.com", "newperson", "New Person")

    assert user.first_login_at is not None
    event = await InstanceEvent.get(category=InstanceEventCategory.FIRST_LOGIN)
    assert event.actor_id == user.id
    assert event.subject_user_id == user.id
    assert event.detail == {"provider": "github"}


async def test_resolve_oauth_identity_creates_link_on_email_match_logs_oauth_linked(db):
    from mulchd.auth import create_user
    from mulchd.connect import _resolve_oauth_identity
    from mulchd.models import InstanceEvent, InstanceEventCategory

    user, _ = await create_user("ssouser", "SSO User", email="sso2@example.com")

    result = await _resolve_oauth_identity("github", "gh-777", "sso2@example.com")

    assert result is not None
    event = await InstanceEvent.get(category=InstanceEventCategory.OAUTH_LINKED)
    assert event.subject_user_id == user.id
    assert event.detail == {"provider": "github"}


async def test_resolve_oauth_identity_existing_link_does_not_relog(db):
    from mulchd.auth import create_user
    from mulchd.connect import _resolve_oauth_identity
    from mulchd.models import InstanceEvent, InstanceEventCategory, OAuthIdentity

    user, _ = await create_user("ssouser2", "SSO User 2")
    await OAuthIdentity.create(user=user, provider="github", sub="gh-888")

    await _resolve_oauth_identity("github", "gh-888", "any@email.com")

    count = await InstanceEvent.filter(category=InstanceEventCategory.OAUTH_LINKED).count()
    assert count == 0


async def test_token_login_first_time_sets_first_login_and_logs_event(client, db):
    from mulchd.auth import create_user
    from mulchd.models import InstanceEvent, InstanceEventCategory, User

    user, token = await create_user("tokenfirstlogin", "Token First Login")
    assert user.first_login_at is None

    resp = await client.post(
        "/connect", data={"token": token, "remember_me": ""}, follow_redirects=False
    )
    assert resp.status_code == 303

    await user.refresh_from_db()
    assert user.first_login_at is not None
    event = await InstanceEvent.get(category=InstanceEventCategory.FIRST_LOGIN)
    assert event.subject_user_id == user.id
    assert event.detail == {"provider": "token"}


async def test_token_login_second_time_does_not_relog(client, db):
    from mulchd.auth import create_user
    from mulchd.models import InstanceEvent, InstanceEventCategory

    user, token = await create_user("tokensecondlogin", "Token Second Login")
    await client.post("/connect", data={"token": token, "remember_me": ""})

    await client.post("/connect", data={"token": token, "remember_me": ""})

    count = await InstanceEvent.filter(category=InstanceEventCategory.FIRST_LOGIN).count()
    assert count == 1


async def test_oauth_login_bootstraps_matching_admin_email(db, monkeypatch):
    from mulchd.admin_grants import is_superadmin, maybe_bootstrap_admin
    from mulchd.auth import create_user
    import mulchd.config as config_mod

    monkeypatch.setattr(config_mod.settings, "bootstrap_admin_email", "founder@acme.com")
    user, _ = await create_user("founder", "Founder", email="founder@acme.com")

    await maybe_bootstrap_admin(user)

    assert await is_superadmin(user) is True
