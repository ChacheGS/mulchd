import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

# ── OAuth routes ─────────────────────────────────────────────────────────────


async def test_oauth_start_unknown_provider_returns_404(client):
    resp = await client.get("/connect/auth/unknown/start", follow_redirects=False)
    assert resp.status_code == 404


async def test_oauth_callback_unknown_provider_returns_404(client):
    resp = await client.get("/connect/auth/unknown/callback?code=x&state=y")
    assert resp.status_code == 404


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


async def test_oauth_login_bootstraps_matching_admin_email(db, monkeypatch):
    from mulchd.admin_grants import is_superadmin, maybe_bootstrap_admin
    from mulchd.auth import create_user
    import mulchd.config as config_mod

    monkeypatch.setattr(config_mod.settings, "bootstrap_admin_email", "founder@acme.com")
    user, _ = await create_user("founder", "Founder", email="founder@acme.com")

    await maybe_bootstrap_admin(user)

    assert await is_superadmin(user) is True
