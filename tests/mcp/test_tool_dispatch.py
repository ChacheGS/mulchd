"""
list_tools / call_tool dispatch and RecordEvent audit-trail tests.
"""

from mulchd.mcp.context import _ctx
import pytest
from mulchd.models import Role
from mulchd.mcp.tier2 import call_tool
from tests.mcp.conftest import ctx, _make_fake_delete


async def test_list_tools_hides_mutating_tools_from_reader(team, data_path):
    from mulchd.mcp.tier2 import list_tools

    t = team
    token = _ctx.set(ctx(t.carlos, t.org, t.infra, role=Role.READER))
    try:
        tools = await list_tools()
    finally:
        _ctx.reset(token)

    names = {tool.name for tool in tools}
    assert names == {
        "read_records",
        "search_records",
        "list_domains",
        "get_record_schema",
        "get_record_history",
    }


async def test_list_tools_shows_everything_to_writer(team, data_path):
    from mulchd.mcp.tier2 import TIER2_TOOLS, list_tools

    t = team
    token = _ctx.set(ctx(t.carlos, t.org, t.infra, role=Role.WRITER))
    try:
        tools = await list_tools()
    finally:
        _ctx.reset(token)

    assert {tool.name for tool in tools} == {tool.name for tool in TIER2_TOOLS}


async def test_list_tools_shows_everything_to_admin(team, data_path):
    from mulchd.mcp.tier2 import TIER2_TOOLS, list_tools

    t = team
    token = _ctx.set(ctx(t.carlos, t.org, t.infra, role=Role.ADMIN))
    try:
        tools = await list_tools()
    finally:
        _ctx.reset(token)

    assert {tool.name for tool in tools} == {tool.name for tool in TIER2_TOOLS}


async def test_list_tools_raises_without_auth_context():
    from mulchd.mcp.tier2 import list_tools

    with pytest.raises(ValueError, match="No auth context"):
        await list_tools()


async def test_call_tool_still_rejects_reader_for_hidden_tool(team, data_path):
    """The advertised list changing must not weaken the actual enforcement —
    a READER token calling a hidden tool directly still gets the existing
    specific rejection message."""
    t = team
    token = _ctx.set(ctx(t.carlos, t.org, t.infra, role=Role.READER))
    try:
        with pytest.raises(ValueError, match="reader role cannot edit records"):
            await call_tool("edit_record", {"record_id": "mx-whatever", "domain": "infra", "content": "x"})
    finally:
        _ctx.reset(token)


async def test_record_events_written_for_write_edit_delete(team, data_path, fake_write_record):
    """RecordEvent rows are created for every mutating action (write, edit, delete)."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _delete_record, _edit_record
    from mulchd.models import RecordEvent

    t = team
    expertise = data_path / "acme" / "infra" / ".mulch" / "expertise"

    await mcp_tier2._record_expertise(
        {
            "domain": "audit-test",
            "type": "convention",
            "classification": "tactical",
            "content": "v1",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    records_after_write = await mcp_tier2._read_expertise(
        {"domains": ["audit-test"]}, ctx(t.carlos, t.org, t.infra)
    )
    record_id = records_after_write[1]["records"][0]["id"]

    async def _noop_edit(m_dir, domain, rid, updates):
        pass

    orig_edit = mcp_tier2.edit_record
    mcp_tier2.edit_record = _noop_edit
    await _edit_record(
        {"record_id": record_id, "domain": "audit-test", "content": "v2"},
        ctx(t.carlos, t.org, t.infra),
    )
    mcp_tier2.edit_record = orig_edit

    mcp_tier2.delete_record = _make_fake_delete(expertise)
    await _delete_record(
        {"record_id": record_id, "domain": "audit-test"}, ctx(t.carlos, t.org, t.infra)
    )

    events = await RecordEvent.filter(record_id=record_id).values_list("action", flat=True)
    assert set(events) == {"write", "edit", "delete"}
