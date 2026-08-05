"""
read_resource must apply the same edit/outcome-staleness annotations that
read_records and search_records already apply — otherwise a record that's
been edited since its last confirmed outcome renders as a clean confirmed
success on the resource path while showing stale on the tool path.
"""

from datetime import datetime, timezone

from mulchd.mcp.context import auth_ctx
from mulchd.models import RecordEdit
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
