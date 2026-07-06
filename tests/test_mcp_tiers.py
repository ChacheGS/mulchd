import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.mark.no_db
def test_context_vars_start_as_none():
    from mulchd.mcp.context import _ctx

    assert _ctx.get() is None


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
async def test_tier1_get_setup_instructions_references_connect(monkeypatch):
    from mulchd.config import settings

    monkeypatch.setattr(settings, "base_url", "https://test.example.com")
    monkeypatch.setattr(settings, "admin_contact", None)
    from mulchd.mcp.tier1 import _get_setup_instructions

    result = await _get_setup_instructions()
    assert "test.example.com" in result[0].text
    assert "/connect" in result[0].text
    assert "/onboard" not in result[0].text


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
def test_tier2_tool_list_has_eight_knowledge_tools():
    from mulchd.mcp.tier2 import TIER2_TOOLS

    names = {t.name for t in TIER2_TOOLS}
    assert names == {
        "read_records",
        "write_record",
        "search_records",
        "list_domains",
        "get_recent",
        "get_record_schema",
        "edit_record",
        "delete_record",
    }
    assert "mint_project_token" not in names
    assert "get_setup_instructions" not in names


@pytest.mark.no_db
def test_tier2_server_has_session_workflow_instructions():
    from mulchd.mcp.tier2 import SESSION_WORKFLOW, tier2_server

    opts = tier2_server.create_initialization_options()
    assert opts.instructions == SESSION_WORKFLOW
    assert len(SESSION_WORKFLOW) > 200


async def test_resolve_tier1_with_no_auth(client):
    from starlette.requests import Request

    from mulchd.main import resolve_mcp_tier

    scope = {"type": "http", "method": "POST", "path": "/mcp", "headers": [], "query_string": b""}
    req = Request(scope)
    tier, ctx = await resolve_mcp_tier(req)
    assert tier == "tier1"
    assert ctx is None


# ---------------------------------------------------------------------------
# Regression tests — cross-evaluation findings (2026-07-03)
# ---------------------------------------------------------------------------


@pytest.mark.no_db
def test_no_tool_description_says_expertise_record():
    """delete_record and get_recent previously described their subject as
    'expertise record' after the bulk rename. All 8 tools should use 'record'."""
    from mulchd.mcp.tier2 import TIER2_TOOLS

    for tool in TIER2_TOOLS:
        assert "expertise record" not in (
            tool.description or ""
        ), f"Tool '{tool.name}' still contains stale wording 'expertise record'"


@pytest.mark.no_db
def test_write_record_schema_exposes_date_for_decisions():
    """get_record_schema advertises decision.date as an optional field, but
    write_record must also expose it so clients can actually set it."""
    from mulchd.mcp.tier2 import TIER2_TOOLS

    write_tool = next(t for t in TIER2_TOOLS if t.name == "write_record")
    assert (
        "date" in write_tool.inputSchema["properties"]
    ), "write_record must include 'date' to match what get_record_schema advertises"


@pytest.mark.no_db
def test_search_records_filter_param_named_owner_not_author():
    """search_records filters on the 'owner' field in records, so the parameter
    should be named 'owner' for consistency — not 'author'."""
    from mulchd.mcp.tier2 import TIER2_TOOLS

    search_tool = next(t for t in TIER2_TOOLS if t.name == "search_records")
    props = search_tool.inputSchema["properties"]
    assert "owner" in props, "search_records filter parameter should be named 'owner'"
    assert (
        "author" not in props
    ), "search_records should not use 'author' (inconsistent with stored field)"


async def test_resolve_tier2_with_project_token(db):
    from starlette.requests import Request

    from mulchd.auth import create_project_token, create_user
    from mulchd.main import resolve_mcp_tier
    from mulchd.models import Organization, Project, Role, User, UserMembership

    _, _ = await create_user("bob", "Bob")
    user = await User.get(username="bob")
    org = await Organization.create(slug="acme", display_name="Acme")
    proj = await Project.create(slug="demo", display_name="Demo", org=org)
    await UserMembership.create(user=user, project=proj, role=Role.WRITER)
    _, token = await create_project_token(user, proj, label="test")

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
        "query_string": b"",
    }
    request = Request(scope)
    tier, ctx = await resolve_mcp_tier(request)
    assert tier == "tier2"
    assert ctx is not None
    assert ctx.project.slug == "demo"
