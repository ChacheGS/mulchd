from mulchd.config import settings
from mulchd.oauth import get_configured_providers


def test_no_providers_configured():
    assert get_configured_providers() == []


def test_github_provider_configured(monkeypatch):
    monkeypatch.setattr(settings, "github_client_id", "id123")
    monkeypatch.setattr(settings, "github_client_secret", "secret456")
    assert ("github", "GitHub") in get_configured_providers()


def test_oidc_display_name(monkeypatch):
    monkeypatch.setattr(
        settings, "oidc_discovery_url", "https://accounts.google.com/.well-known/openid-configuration"
    )
    monkeypatch.setattr(settings, "oidc_client_id", "cid")
    monkeypatch.setattr(settings, "oidc_client_secret", "csec")
    monkeypatch.setattr(settings, "oidc_display_name", "Google")
    assert ("oidc", "Google") in get_configured_providers()


def test_oidc_default_display_name(monkeypatch):
    monkeypatch.setattr(settings, "oidc_discovery_url", "https://example.com/.well-known/openid-configuration")
    monkeypatch.setattr(settings, "oidc_client_id", "cid")
    monkeypatch.setattr(settings, "oidc_client_secret", "csec")
    assert ("oidc", "SSO") in get_configured_providers()
