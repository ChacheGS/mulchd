import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.mark.no_db
def test_context_vars_start_as_none():
    from mulchd.mcp.context import _ctx, _global_ctx
    assert _ctx.get() is None
    assert _global_ctx.get() is None


@pytest.mark.no_db
def test_resolved_base_url_derived_from_host_port():
    from mulchd.config import Settings
    s = Settings(secret_key="x", admin_password="x", host="localhost", port=9000)
    assert s.resolved_base_url == "http://localhost:9000"


@pytest.mark.no_db
def test_resolved_base_url_explicit_overrides_derivation():
    from mulchd.config import Settings
    s = Settings(secret_key="x", admin_password="x", base_url="https://mulchd.example.com/")
    assert s.resolved_base_url == "https://mulchd.example.com"


@pytest.mark.no_db
def test_admin_contact_defaults_to_none():
    from mulchd.config import Settings
    s = Settings(secret_key="x", admin_password="x")
    assert s.admin_contact is None


@pytest.mark.no_db
def test_render_plain_contains_server_url():
    from mulchd.mcp.onboarding import render_onboarding_text
    text = render_onboarding_text("https://mulchd.example.com", "plain")
    assert "https://mulchd.example.com" in text


@pytest.mark.no_db
def test_render_plain_contains_both_client_shapes():
    from mulchd.mcp.onboarding import render_onboarding_text
    text = render_onboarding_text("https://mulchd.example.com", "plain")
    assert "mcp-remote" in text
    assert ".mcp.json" in text


@pytest.mark.no_db
def test_render_html_contains_server_url():
    from mulchd.mcp.onboarding import render_onboarding_text
    text = render_onboarding_text("https://mulchd.example.com", "html")
    assert "https://mulchd.example.com" in text


@pytest.mark.no_db
def test_render_admin_contact_included_when_set():
    from mulchd.mcp.onboarding import render_onboarding_text
    text = render_onboarding_text("https://x.com", "plain", admin_contact="help@example.com")
    assert "help@example.com" in text


@pytest.mark.no_db
def test_render_admin_contact_absent_when_none():
    from mulchd.mcp.onboarding import render_onboarding_text
    sentinel = "help@example.com"
    text = render_onboarding_text("https://x.com", "plain", admin_contact=None)
    assert sentinel not in text


@pytest.mark.no_db
def test_render_html_and_plain_same_url():
    from mulchd.mcp.onboarding import render_onboarding_text
    url = "https://mulchd.example.com"
    assert url in render_onboarding_text(url, "html")
    assert url in render_onboarding_text(url, "plain")
