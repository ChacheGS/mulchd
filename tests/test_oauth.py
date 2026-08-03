def test_no_providers_configured():
    from mulchd.oauth import get_configured_providers

    assert get_configured_providers() == []


def test_github_provider_configured(monkeypatch):
    from mulchd.config import settings
    from mulchd.oauth import ProviderInfo, get_configured_providers

    monkeypatch.setattr(settings, "github_client_id", "id123")
    monkeypatch.setattr(settings, "github_client_secret", "secret456")
    assert ProviderInfo(key="github", display_name="GitHub", logo_url=None) in get_configured_providers()


def test_oidc_provider_with_display_name_and_logo(monkeypatch):
    from mulchd.oauth import ProviderInfo, get_configured_providers

    monkeypatch.setenv(
        "MULCHD_OIDC_GOOGLE_DISCOVERY_URL",
        "https://accounts.google.com/.well-known/openid-configuration",
    )
    monkeypatch.setenv("MULCHD_OIDC_GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("MULCHD_OIDC_GOOGLE_CLIENT_SECRET", "csec")
    monkeypatch.setenv("MULCHD_OIDC_GOOGLE_DISPLAY_NAME", "Google")
    monkeypatch.setenv("MULCHD_OIDC_GOOGLE_LOGO_URL", "https://example.com/google.svg")

    providers = get_configured_providers()
    assert ProviderInfo(
        key="oidc_google", display_name="Google", logo_url="https://example.com/google.svg"
    ) in providers


def test_oidc_provider_default_display_name_and_no_logo(monkeypatch):
    from mulchd.oauth import ProviderInfo, get_configured_providers

    monkeypatch.setenv(
        "MULCHD_OIDC_OKTA_DISCOVERY_URL", "https://okta.example.com/.well-known/openid-configuration"
    )
    monkeypatch.setenv("MULCHD_OIDC_OKTA_CLIENT_ID", "cid")
    monkeypatch.setenv("MULCHD_OIDC_OKTA_CLIENT_SECRET", "csec")

    providers = get_configured_providers()
    assert ProviderInfo(key="oidc_okta", display_name="Okta", logo_url=None) in providers


def test_oidc_provider_missing_client_secret_is_skipped(monkeypatch):
    from mulchd.oauth import get_configured_providers

    monkeypatch.setenv(
        "MULCHD_OIDC_BROKEN_DISCOVERY_URL", "https://broken.example.com/.well-known/openid-configuration"
    )
    monkeypatch.setenv("MULCHD_OIDC_BROKEN_CLIENT_ID", "cid")
    # no MULCHD_OIDC_BROKEN_CLIENT_SECRET set

    providers = get_configured_providers()
    assert all(p.key != "oidc_broken" for p in providers)


def test_multiple_oidc_providers_configured_simultaneously(monkeypatch):
    from mulchd.oauth import get_configured_providers

    monkeypatch.setenv(
        "MULCHD_OIDC_GOOGLE_DISCOVERY_URL",
        "https://accounts.google.com/.well-known/openid-configuration",
    )
    monkeypatch.setenv("MULCHD_OIDC_GOOGLE_CLIENT_ID", "gid")
    monkeypatch.setenv("MULCHD_OIDC_GOOGLE_CLIENT_SECRET", "gsec")
    monkeypatch.setenv(
        "MULCHD_OIDC_OKTA_DISCOVERY_URL", "https://okta.example.com/.well-known/openid-configuration"
    )
    monkeypatch.setenv("MULCHD_OIDC_OKTA_CLIENT_ID", "oid")
    monkeypatch.setenv("MULCHD_OIDC_OKTA_CLIENT_SECRET", "osec")

    keys = {p.key for p in get_configured_providers()}
    assert {"oidc_google", "oidc_okta"} <= keys

    oidc_keys = [p.key for p in get_configured_providers() if p.key.startswith("oidc_")]
    assert oidc_keys == ["oidc_google", "oidc_okta"]
