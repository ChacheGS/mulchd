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


@pytest.mark.no_db
def test_tier1_tool_list_has_exactly_one_tool():
    from mulchd.mcp.tier1 import TIER1_TOOLS
    assert len(TIER1_TOOLS) == 1
    assert TIER1_TOOLS[0].name == "get_setup_instructions"


@pytest.mark.no_db
def test_tier1_server_has_no_instructions():
    from mulchd.mcp.tier1 import tier1_server
    opts = tier1_server.create_initialization_options()
    assert opts.instructions is None


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_tier1_get_setup_instructions_returns_onboard_link(monkeypatch):
    from mulchd.config import settings
    monkeypatch.setattr(settings, "base_url", "https://test.example.com")
    monkeypatch.setattr(settings, "admin_contact", None)
    from mulchd.mcp.tier1 import _get_setup_instructions
    result = await _get_setup_instructions()
    assert len(result) == 1
    assert "test.example.com" in result[0].text
    assert "/onboard" in result[0].text


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_tier1_get_setup_instructions_includes_contact(monkeypatch):
    from mulchd.config import settings
    monkeypatch.setattr(settings, "base_url", "https://test.example.com")
    monkeypatch.setattr(settings, "admin_contact", "ops@example.com")
    from mulchd.mcp.tier1 import _get_setup_instructions
    result = await _get_setup_instructions()
    assert "ops@example.com" in result[0].text
