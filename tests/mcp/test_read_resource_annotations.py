"""
read_resource must apply the same edit/outcome-staleness annotations that
read_records and search_records already apply — otherwise a record that's
been edited since its last confirmed outcome renders as a clean confirmed
success on the resource path while showing stale on the tool path.
"""

from datetime import datetime, timezone

from mulchd.mcp.context import auth_ctx
from mulchd.models import RecordEdit, ToolCall
from tests.mcp.conftest import _jot, ctx


async def test_read_resource_shows_edit_and_staleness_markers(team, data_path):
    from mcp.types import ReadResourceRequestParams

    from mulchd.mcp.tier2 import read_resource

    t = team
    record = _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="Updated rule",
        owner="carlos",
        outcomes=[{"status": "success", "recorded_at": "2026-01-01T00:00:00+00:00"}],
    )
    await RecordEdit.create(
        record_id=record["id"],
        project=t.infra,
        domain="infra",
        actor=t.carlos,
        before_snapshot={"content": "Original rule"},
        at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )

    token = auth_ctx.set(ctx(t.carlos, t.org, t.infra))
    try:
        result = await read_resource(
            None, ReadResourceRequestParams(uri="mulchd://acme/infra/domain/infra")
        )
    finally:
        auth_ctx.reset(token)

    text = result.contents[0].text
    assert "edited 1×" in text
    assert "⚠ stale (edited since last confirmed)" in text


async def test_read_resource_renders_files_and_evidence(team, data_path):
    from mcp.types import ReadResourceRequestParams

    from mulchd.mcp.tier2 import read_resource

    t = team
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="pattern",
        classification="tactical",
        content="Retry with backoff",
        owner="carlos",
        files=["src/mulchd/mcp/tier2.py"],
        evidence={"commit": "abc123"},
    )

    token = auth_ctx.set(ctx(t.carlos, t.org, t.infra))
    try:
        result = await read_resource(
            None, ReadResourceRequestParams(uri="mulchd://acme/infra/domain/infra")
        )
    finally:
        auth_ctx.reset(token)

    text = result.contents[0].text
    assert "files: src/mulchd/mcp/tier2.py" in text
    assert "evidence: commit=abc123" in text


async def test_read_resource_caps_response_size(team, data_path):
    """resources/read has no limit/cursor params a client could pass, unlike
    read_records — it must still cap a single response instead of rendering
    an entire, potentially huge domain in one shot."""
    from mcp.types import ReadResourceRequestParams

    from mulchd.mcp.tier2 import read_resource
    from mulchd.policies import POLICIES

    _RESOURCE_READ_LIMIT = POLICIES["default_page_size"].default

    t = team
    for i in range(_RESOURCE_READ_LIMIT + 5):
        _jot(
            data_path,
            "acme",
            "infra",
            "infra",
            type="convention",
            classification="observational",
            content=f"rule {i}",
            owner="carlos",
        )

    token = auth_ctx.set(ctx(t.carlos, t.org, t.infra))
    try:
        result = await read_resource(
            None, ReadResourceRequestParams(uri="mulchd://acme/infra/domain/infra")
        )
    finally:
        auth_ctx.reset(token)

    text = result.contents[0].text
    assert text.count("[infra/convention/observational]") == _RESOURCE_READ_LIMIT
    assert f"Showing {_RESOURCE_READ_LIMIT} of {_RESOURCE_READ_LIMIT + 5} records" in text
    assert "read_records(domains=['infra'])" in text


async def test_read_resource_records_usage(team, data_path):
    """A resources/read call left no trace in the ToolCall table that feeds
    the admin usage panel — call_tool tracks every tool call, but the same
    content read via a resource was invisible to it."""
    import asyncio

    from mcp.types import ReadResourceRequestParams

    from mulchd.mcp.tier2 import read_resource

    t = team
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="Tracked read",
        owner="carlos",
    )

    token = auth_ctx.set(ctx(t.carlos, t.org, t.infra))
    try:
        await read_resource(
            None, ReadResourceRequestParams(uri="mulchd://acme/infra/domain/infra")
        )
    finally:
        auth_ctx.reset(token)
    # _record_tool_call is scheduled as a fire-and-forget background task.
    await asyncio.sleep(0.01)

    call = await ToolCall.filter(project=t.infra, tool="resources/read").order_by("-id").first()
    assert call is not None
    assert call.author_id == t.carlos.id


async def test_read_resource_cap_comes_from_policy(team, data_path, monkeypatch):
    from mcp.types import ReadResourceRequestParams

    from mulchd.mcp.tier2 import read_resource

    t = team
    monkeypatch.setenv("MULCHD_POLICY_DEFAULT_PAGE_SIZE", "2")
    for i in range(3):
        _jot(
            data_path, "acme", "infra", "infra",
            type="convention", classification="tactical", content=f"r{i}", owner="carlos",
        )

    token = auth_ctx.set(ctx(t.carlos, t.org, t.infra))
    try:
        result = await read_resource(
            None, ReadResourceRequestParams(uri="mulchd://acme/infra/domain/infra")
        )
    finally:
        auth_ctx.reset(token)

    text = result.contents[0].text
    assert "Showing 2 of 3 records" in text
