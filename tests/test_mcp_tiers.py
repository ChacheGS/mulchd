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


@pytest.mark.no_db
def test_tier2_tool_list_has_four_tools():
    from mulchd.mcp.tier2 import TIER2_TOOLS
    names = {t.name for t in TIER2_TOOLS}
    assert names == {
        "list_my_projects",
        "mint_project_token",
        "list_project_tokens",
        "revoke_project_token",
    }


@pytest.mark.no_db
def test_tier2_server_has_no_instructions():
    from mulchd.mcp.tier2 import tier2_server
    assert tier2_server.create_initialization_options().instructions is None


@pytest.mark.no_db
def test_build_next_steps_interpolates_values():
    from mulchd.mcp.tier2 import _build_next_steps
    result = _build_next_steps("https://example.com", "acme", "demo", "tok-abc")
    assert "https://example.com/mcp" in result
    assert "mulchd-demo" in result
    assert "mulchd-acme-demo" in result
    assert "tok-abc" in result
    assert "MULCHD_TOKEN_ACME_DEMO" in result


@pytest.mark.no_db
def test_build_next_steps_uppercases_slugs_with_hyphens():
    from mulchd.mcp.tier2 import _build_next_steps
    result = _build_next_steps("https://x.com", "my-org", "my-project", "t")
    assert "MULCHD_TOKEN_MY_ORG_MY_PROJECT" in result


@pytest.mark.no_db
def test_tier3_tool_list_has_eight_knowledge_tools():
    from mulchd.mcp.tier3 import TIER3_TOOLS
    names = {t.name for t in TIER3_TOOLS}
    assert names == {
        "read_expertise", "record_expertise", "search_expertise", "list_domains",
        "get_recent", "get_record_schema", "edit_record", "delete_record",
    }
    assert "mint_project_token" not in names
    assert "get_setup_instructions" not in names


@pytest.mark.no_db
def test_tier3_server_has_session_workflow_instructions():
    from mulchd.mcp.tier3 import tier3_server, SESSION_WORKFLOW
    opts = tier3_server.create_initialization_options()
    assert opts.instructions == SESSION_WORKFLOW
    assert len(SESSION_WORKFLOW) > 200


async def test_onboard_returns_200_with_config_snippets(client):
    resp = await client.get("/onboard")
    assert resp.status_code == 200
    assert "mcp-remote" in resp.text
    assert ".mcp.json" in resp.text


async def test_onboard_no_contact_when_unset(client, monkeypatch):
    from mulchd.config import settings
    monkeypatch.setattr(settings, "admin_contact", None)
    resp = await client.get("/onboard")
    assert resp.status_code == 200
    assert "ops@example.com" not in resp.text


async def test_onboard_shows_contact_when_set(client, monkeypatch):
    from mulchd.config import settings
    monkeypatch.setattr(settings, "admin_contact", "ops@example.com")
    resp = await client.get("/onboard")
    assert resp.status_code == 200
    assert "ops@example.com" in resp.text


async def test_resolve_tier1_with_no_auth(client):
    from starlette.requests import Request
    from mulchd.main import resolve_mcp_tier
    scope = {"type": "http", "method": "POST", "path": "/mcp",
             "headers": [], "query_string": b""}
    req = Request(scope)
    tier, ctx = await resolve_mcp_tier(req)
    assert tier == "tier1"
    assert ctx is None


async def test_resolve_tier2_with_global_token(db):
    from starlette.requests import Request
    from mulchd.auth import create_user
    from mulchd.main import resolve_mcp_tier
    _, token = await create_user("jorge", "Jorge")
    scope = {
        "type": "http", "method": "POST", "path": "/mcp",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
        "query_string": b"",
    }
    req = Request(scope)
    tier, ctx = await resolve_mcp_tier(req)
    assert tier == "tier2"
    assert ctx.username == "jorge"


async def test_resolve_tier3_with_project_token(db):
    from starlette.requests import Request
    from mulchd.auth import create_project_token, create_user
    from mulchd.main import resolve_mcp_tier
    from mulchd.models import Organization, Project, UserMembership, Role
    user, _ = await create_user("jorge", "Jorge")
    org = await Organization.create(slug="acme", display_name="Acme")
    proj = await Project.create(slug="demo", display_name="Demo", org=org)
    await UserMembership.create(user=user, project=proj, role=Role.WRITER)
    _, token = await create_project_token(user, proj, label="test")
    scope = {
        "type": "http", "method": "POST", "path": "/mcp",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
        "query_string": b"",
    }
    req = Request(scope)
    tier, ctx = await resolve_mcp_tier(req)
    assert tier == "tier3"
    assert ctx.project.slug == "demo"
