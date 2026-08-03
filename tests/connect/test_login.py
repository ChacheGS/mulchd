import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

from tests.connect.conftest import _authed_client

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


async def test_login_redirects_to_return_to_after_token_login(client, alice_and_project):
    user, token, org, project = alice_and_project
    await client.get("/connect", params={"return_to": "/connect/oauth-consent?client_id=x"})
    resp = await client.post(
        "/connect", data={"token": token, "remember_me": ""}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/connect/oauth-consent?client_id=x"


async def test_login_ignores_unsafe_return_to(client, alice_and_project):
    user, token, org, project = alice_and_project
    await client.get("/connect", params={"return_to": "https://evil.example/steal"})
    resp = await client.post(
        "/connect", data={"token": token, "remember_me": ""}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/connect/projects"


async def test_connect_entry_page_has_no_sso_buttons_without_config(client):
    """With no OAuth env vars set in tests, entry page must not show SSO buttons."""
    resp = await client.get("/connect")
    assert resp.status_code == 200
    assert "Sign in with" not in resp.text


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


async def test_connect_entry_page_shows_github_logo_when_configured(client, monkeypatch):
    from mulchd.config import settings

    monkeypatch.setattr(settings, "github_client_id", "id123")
    monkeypatch.setattr(settings, "github_client_secret", "secret456")

    resp = await client.get("/connect")
    assert resp.status_code == 200
    assert "GitHub logo" in resp.text
    assert "<svg" in resp.text


async def test_connect_entry_page_shows_configured_oidc_logo(client, monkeypatch):
    monkeypatch.setenv(
        "MULCHD_OIDC_GOOGLE_DISCOVERY_URL",
        "https://accounts.google.com/.well-known/openid-configuration",
    )
    monkeypatch.setenv("MULCHD_OIDC_GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("MULCHD_OIDC_GOOGLE_CLIENT_SECRET", "csec")
    monkeypatch.setenv("MULCHD_OIDC_GOOGLE_DISPLAY_NAME", "Google")
    monkeypatch.setenv("MULCHD_OIDC_GOOGLE_LOGO_URL", "https://example.com/google-logo.svg")

    resp = await client.get("/connect")
    assert resp.status_code == 200
    assert 'src="https://example.com/google-logo.svg"' in resp.text
    assert "Google logo" in resp.text


async def test_connect_entry_page_falls_back_to_generic_icon_without_logo_url(client, monkeypatch):
    monkeypatch.setenv(
        "MULCHD_OIDC_OKTA_DISCOVERY_URL", "https://okta.example.com/.well-known/openid-configuration"
    )
    monkeypatch.setenv("MULCHD_OIDC_OKTA_CLIENT_ID", "cid")
    monkeypatch.setenv("MULCHD_OIDC_OKTA_CLIENT_SECRET", "csec")

    resp = await client.get("/connect")
    assert resp.status_code == 200
    assert "Okta logo" in resp.text
    assert "<img" not in resp.text
    assert "<svg" in resp.text
