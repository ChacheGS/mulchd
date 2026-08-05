"""
list_tools / call_tool dispatch and RecordEvent audit-trail tests.
"""

import asyncio
from types import SimpleNamespace

import pytest

from mulchd.mcp.context import auth_ctx
from mulchd.mcp.tier2 import call_tool
from mulchd.models import Role, ToolCall
from tests.mcp.conftest import _make_fake_delete, ctx


async def test_list_tools_hides_mutating_tools_from_reader(team, data_path):
    from mulchd.mcp.tier2 import list_tools

    t = team
    token = auth_ctx.set(ctx(t.carlos, t.org, t.infra, role=Role.READER))
    try:
        result = await list_tools(None, None)
    finally:
        auth_ctx.reset(token)

    names = {tool.name for tool in result.tools}
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
    token = auth_ctx.set(ctx(t.carlos, t.org, t.infra, role=Role.WRITER))
    try:
        result = await list_tools(None, None)
    finally:
        auth_ctx.reset(token)

    assert {tool.name for tool in result.tools} == {tool.name for tool in TIER2_TOOLS}


async def test_list_tools_shows_everything_to_admin(team, data_path):
    from mulchd.mcp.tier2 import TIER2_TOOLS, list_tools

    t = team
    token = auth_ctx.set(ctx(t.carlos, t.org, t.infra, role=Role.ADMIN))
    try:
        result = await list_tools(None, None)
    finally:
        auth_ctx.reset(token)

    assert {tool.name for tool in result.tools} == {tool.name for tool in TIER2_TOOLS}


async def test_list_tools_raises_without_auth_context():
    from mulchd.mcp.tier2 import list_tools

    with pytest.raises(ValueError, match="No auth context"):
        await list_tools(None, None)


async def test_call_tool_still_rejects_reader_for_hidden_tool(team, data_path):
    """The advertised list changing must not weaken the actual enforcement —
    a READER token calling a hidden tool directly still gets the existing
    specific rejection message."""
    from mcp.types import CallToolRequestParams

    t = team
    token = auth_ctx.set(ctx(t.carlos, t.org, t.infra, role=Role.READER))
    try:
        result = await call_tool(
            None,
            CallToolRequestParams(
                name="edit_record",
                arguments={"record_id": "mx-whatever", "domain": "infra", "content": "x"},
            ),
        )
    finally:
        auth_ctx.reset(token)
    assert result.is_error is True
    assert "reader role cannot edit records" in result.content[0].text


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


async def test_call_tool_records_negotiated_protocol_version(team, data_path):
    """The ToolCall row created for a dispatch persists whatever protocol
    version the SDK's ServerRequestContext reports, not a hardcoded default."""
    from mcp.types import CallToolRequestParams

    t = team
    fake_sdk_ctx = SimpleNamespace(protocol_version="2026-06-18", request=None)
    token = auth_ctx.set(ctx(t.carlos, t.org, t.infra, role=Role.READER))
    try:
        await call_tool(
            fake_sdk_ctx,
            CallToolRequestParams(name="list_domains", arguments={}),
        )
    finally:
        auth_ctx.reset(token)

    # _record_tool_call is scheduled as a fire-and-forget background task;
    # give the event loop a turn to let it complete before asserting.
    await asyncio.sleep(0.01)

    call = await ToolCall.filter(project=t.infra, tool="list_domains").order_by("-id").first()
    assert call is not None
    assert call.protocol_version == "2026-06-18"


async def test_call_tool_records_unknown_protocol_version_without_sdk_context(team, data_path):
    """When call_tool is invoked without a real SDK context (as in most of
    this file's direct-dispatch tests), the recorded protocol_version falls
    back to the "unknown" sentinel rather than crashing."""
    from mcp.types import CallToolRequestParams

    t = team
    token = auth_ctx.set(ctx(t.carlos, t.org, t.infra, role=Role.READER))
    try:
        await call_tool(
            None,
            CallToolRequestParams(name="list_domains", arguments={}),
        )
    finally:
        auth_ctx.reset(token)

    await asyncio.sleep(0.01)

    call = await ToolCall.filter(project=t.infra, tool="list_domains").order_by("-id").first()
    assert call is not None
    assert call.protocol_version == "unknown"
