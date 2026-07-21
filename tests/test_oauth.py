import importlib
import pytest


def _reload(monkeypatch, env: dict):
    """Set env vars and reload config + oauth modules."""
    monkeypatch.setenv("MULCHD_SECRET_KEY", "test")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import mulchd.config as cfg_mod
    import mulchd.oauth as oauth_mod
    importlib.reload(cfg_mod)
    importlib.reload(oauth_mod)
    return oauth_mod


def test_no_providers_configured(monkeypatch):
    oauth_mod = _reload(monkeypatch, {})
    assert oauth_mod.get_configured_providers() == []


def test_github_provider_configured(monkeypatch):
    oauth_mod = _reload(monkeypatch, {
        "MULCHD_GITHUB_CLIENT_ID": "id123",
        "MULCHD_GITHUB_CLIENT_SECRET": "secret456",
    })
    assert ("github", "GitHub") in oauth_mod.get_configured_providers()


def test_oidc_display_name(monkeypatch):
    oauth_mod = _reload(monkeypatch, {
        "MULCHD_OIDC_DISCOVERY_URL": "https://accounts.google.com/.well-known/openid-configuration",
        "MULCHD_OIDC_CLIENT_ID": "cid",
        "MULCHD_OIDC_CLIENT_SECRET": "csec",
        "MULCHD_OIDC_DISPLAY_NAME": "Google",
    })
    assert ("oidc", "Google") in oauth_mod.get_configured_providers()


def test_oidc_default_display_name(monkeypatch):
    oauth_mod = _reload(monkeypatch, {
        "MULCHD_OIDC_DISCOVERY_URL": "https://example.com/.well-known/openid-configuration",
        "MULCHD_OIDC_CLIENT_ID": "cid",
        "MULCHD_OIDC_CLIENT_SECRET": "csec",
    })
    assert ("oidc", "SSO") in oauth_mod.get_configured_providers()
