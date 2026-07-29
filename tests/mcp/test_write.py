"""
write_record / write_* dispatch tool tests.
"""

from mulchd.domains import list_available_domains
from mulchd.mcp.context import _ctx
from mulchd.mulch import MulchError
from pathlib import Path
import json
import pytest
from mulchd.models import Role, UserMembership
from mulchd.mcp.tier2 import _read_expertise, _record_expertise, call_tool
from tests.mcp.conftest import _make_fake_delete, ctx, _jot, ml_available


async def test_cross_user_record_then_read(team, data_path, fake_write_record):
    """jorge writes via _record_expertise; carlos (same project) reads it back."""
    t = team
    await _record_expertise(
        {
            "domain": "infra",
            "type": "convention",
            "classification": "tactical",
            "content": "Use IMDSv2 on all EC2 instances",
        },
        ctx(t.jorge, t.org, t.infra),
    )

    text_content, structured = await _read_expertise(
        {"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra)
    )
    assert "IMDSv2" in text_content[0].text
    assert "jorge" in text_content[0].text


async def test_reader_cannot_write(team, data_path, fake_write_record):
    t = team
    await UserMembership.create(user=t.ana, project=t.infra, role=Role.READER)
    reader_ctx = ctx(t.ana, t.org, t.infra, role=Role.READER)

    with pytest.raises(ValueError, match="reader role cannot write"):
        await _record_expertise(
            {
                "domain": "infra",
                "type": "convention",
                "classification": "observational",
                "content": "test",
            },
            reader_ctx,
        )


async def test_writer_record_returns_confirmation(team, data_path, fake_write_record):
    t = team
    result = await _record_expertise(
        {
            "domain": "infra",
            "type": "convention",
            "classification": "observational",
            "content": "Always enable S3 versioning",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    assert len(result) == 1
    assert "convention" in result[0].text
    assert "infra" in result[0].text


async def test_write_decision_dispatch_creates_decision_record(team, data_path, fake_write_record):
    """The write_decision tool call must inject type='decision' before reaching
    _record_expertise, without the caller having to pass type explicitly."""
    t = team
    token = _ctx.set(ctx(t.carlos, t.org, t.infra))
    try:
        result = await call_tool(
            "write_decision",
            {
                "domain": "infra",
                "classification": "tactical",
                "title": "Use IMDSv2",
                "rationale": "Blocks SSRF-based credential theft",
            },
        )
    finally:
        _ctx.reset(token)
    assert "decision" in result[0].text

    text_content, _ = await _read_expertise({"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra))
    assert "IMDSv2" in text_content[0].text


async def test_write_convention_dispatch_rejects_missing_content(team, data_path, fake_write_record):
    """write_convention must still enforce its required field via the shared
    validation in _record_expertise even though the schema itself has no
    'type' property for the caller to get wrong."""
    t = team
    token = _ctx.set(ctx(t.carlos, t.org, t.infra))
    try:
        with pytest.raises(ValueError, match="requires: content"):
            await call_tool(
                "write_convention",
                {"domain": "infra", "classification": "tactical"},
            )
    finally:
        _ctx.reset(token)


async def test_write_record_validates_required_fields(team, data_path, fake_write_record):
    """write_record raises ValueError when required fields are missing."""
    t = team
    with pytest.raises(ValueError, match="requires"):
        await _record_expertise(
            {
                "domain": "infra",
                "type": "decision",
                "classification": "foundational",
                # missing title and rationale
            },
            ctx(t.carlos, t.org, t.infra),
        )


@ml_available
async def test_live_write_record_succeeds(team, data_path):
    """write_record should complete without error via the live ml CLI."""
    t = team
    result = await _record_expertise(
        {
            "domain": "live-test",
            "type": "convention",
            "classification": "tactical",
            "content": "Always enable S3 versioning on all buckets",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    assert "convention" in result[0].text
    assert "live-test" in result[0].text


@ml_available
async def test_live_write_record_decision_succeeds(team, data_path):
    """A decision record (title + rationale) should also write cleanly via ml."""
    t = team
    result = await _record_expertise(
        {
            "domain": "live-test",
            "type": "decision",
            "classification": "foundational",
            "title": "Use Aurora Serverless for managed DBs",
            "rationale": "Removes the operational burden of instance sizing while staying cost-proportional.",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    assert "decision" in result[0].text


async def test_write_failure_cleans_up_empty_domain(team, data_path, monkeypatch):
    """A write that fails after ml creates the domain file should not leave an orphan."""
    import mulchd.mcp.tier2 as mcp_tier2

    async def _init(m_dir: Path) -> None:
        (m_dir / "expertise").mkdir(parents=True, exist_ok=True)

    async def _write_creates_file_then_fails(m_dir: Path, domain: str, record: dict) -> dict:
        # Simulates ml touching the domain file before its own validation fails.
        (m_dir / "expertise" / f"{domain}.jsonl").touch()
        raise MulchError("simulated ml schema rejection")

    monkeypatch.setattr(mcp_tier2, "init_ml_project", _init)
    monkeypatch.setattr(mcp_tier2, "write_record", _write_creates_file_then_fails)

    t = team
    with pytest.raises(MulchError):
        await _record_expertise(
            {
                "domain": "orphan-test",
                "type": "convention",
                "classification": "tactical",
                "content": "Should not persist",
            },
            ctx(t.carlos, t.org, t.infra),
        )

    domains = await list_available_domains(t.org.slug, t.infra.slug)
    assert not any(d["name"] == "orphan-test" for d in domains)


async def test_record_expertise_rejects_fabricated_supersedes(team, data_path, fake_write_record):
    """The write_* MCP tools reject a supersedes ID that doesn't exist anywhere
    in the project, before anything is written."""
    from mulchd.mcp.tier2 import _record_expertise

    t = team
    with pytest.raises(ValueError, match="supersedes references records that don't exist: mx-ghost"):
        await _record_expertise(
            {
                "type": "decision",
                "domain": "infra",
                "classification": "tactical",
                "title": "New decision",
                "rationale": "Because reasons",
                "supersedes": ["mx-ghost"],
            },
            ctx(t.carlos, t.org, t.infra),
        )
    # Nothing should have been written
    _, structured = await _read_expertise({"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra))
    assert structured["records"] == []


async def test_record_expertise_accepts_valid_cross_domain_supersedes(team, data_path, fake_write_record):
    """A supersedes target in a different domain is accepted — cross-domain
    supersession is a supported, designed-for case."""
    from mulchd.mcp.tier2 import _record_expertise

    t = team
    old = _jot(
        data_path, "acme", "infra", "guardrails",
        type="convention", classification="foundational", content="Old", owner="carlos",
    )
    await _record_expertise(
        {
            "type": "decision",
            "domain": "policies",
            "classification": "foundational",
            "title": "New rule",
            "rationale": "Replaces the old guardrail",
            "supersedes": [old["id"]],
        },
        ctx(t.carlos, t.org, t.infra),
    )
    _, structured = await _read_expertise({"domains": ["policies"]}, ctx(t.carlos, t.org, t.infra))
    assert len(structured["records"]) == 1


async def test_record_expertise_without_references_skips_project_scan(team, data_path, monkeypatch, fake_write_record):
    """A write with no supersedes/relates_to at all must not trigger a
    project-wide scan — get_project_records should not be called."""
    import mulchd.mcp.tier2 as mcp_tier2

    t = team
    called = False
    original = mcp_tier2.get_project_records

    async def _tracking(*a, **kw):
        nonlocal called
        called = True
        return await original(*a, **kw)

    monkeypatch.setattr(mcp_tier2, "get_project_records", _tracking)

    await mcp_tier2._record_expertise(
        {
            "type": "decision",
            "domain": "infra",
            "classification": "tactical",
            "title": "Plain decision",
            "rationale": "No relationships involved",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    assert called is False


async def test_record_expertise_rejects_archived_supersedes_target(team, data_path, fake_write_record):
    """A supersedes target that's been archived (soft-deleted) is rejected the
    same as a fabricated ID — it's no longer live."""
    from mulchd.domains import mulch_dir
    from mulchd.mcp.tier2 import _record_expertise

    t = team
    m_dir = mulch_dir("acme", "infra")
    archive_dir = m_dir / "archive"
    archive_dir.mkdir(parents=True)
    (archive_dir / "infra.jsonl").write_text(
        json.dumps({"id": "mx-archived1", "type": "convention", "classification": "tactical"}) + "\n"
    )
    with pytest.raises(ValueError, match="supersedes references records that don't exist: mx-archived1"):
        await _record_expertise(
            {
                "type": "decision",
                "domain": "infra",
                "classification": "tactical",
                "title": "New decision",
                "rationale": "Because reasons",
                "supersedes": ["mx-archived1"],
            },
            ctx(t.carlos, t.org, t.infra),
        )


async def test_write_record_supersession_warning_on_foundational(
    team, data_path, fake_write_record
):
    """write_record response includes SUPERSESSION WARNING when superseding a foundational record."""
    t = team
    original = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="convention",
        classification="foundational",
        content="Guardrail",
        owner="carlos",
    )
    result = await _record_expertise(
        {
            "domain": "api",
            "type": "convention",
            "classification": "tactical",
            "content": "Weakened",
            "supersedes": [original["id"]],
        },
        ctx(t.carlos, t.org, t.infra),
    )
    text = result[0].text
    assert "SUPERSESSION WARNING" in text
    assert original["id"] in text
    assert "foundational → tactical" in text


async def test_write_record_supersession_warning_same_tier_foundational(
    team, data_path, fake_write_record
):
    """write_record warns even when new record is also foundational (guardrail replacement)."""
    t = team
    original = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="convention",
        classification="foundational",
        content="Guardrail",
        owner="carlos",
    )
    result = await _record_expertise(
        {
            "domain": "api",
            "type": "convention",
            "classification": "foundational",
            "content": "New guardrail",
            "supersedes": [original["id"]],
        },
        ctx(t.carlos, t.org, t.infra),
    )
    text = result[0].text
    assert "SUPERSESSION WARNING" in text
    assert "foundational guardrail replaced" in text


async def test_write_record_no_warning_when_superseding_tactical(
    team, data_path, fake_write_record
):
    """write_record does not warn when superseding a lower-tier record at the same tier."""
    t = team
    original = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="convention",
        classification="tactical",
        content="Old approach",
        owner="carlos",
    )
    result = await _record_expertise(
        {
            "domain": "api",
            "type": "convention",
            "classification": "tactical",
            "content": "New approach",
            "supersedes": [original["id"]],
        },
        ctx(t.carlos, t.org, t.infra),
    )
    assert "SUPERSESSION WARNING" not in result[0].text


async def test_write_rolls_back_jsonl_when_db_metadata_fails(team, data_path, fake_write_record, monkeypatch):
    """If RecordMeta.create fails after the JSONL write already succeeded, the
    record must be removed from disk so the operation fails cleanly instead of
    leaving a record invisible to get_record_history/session grouping."""
    import mulchd.mcp.tier2 as mcp_tier2

    t = team
    expertise = data_path / "acme" / "infra" / ".mulch" / "expertise"
    monkeypatch.setattr(mcp_tier2, "delete_record", _make_fake_delete(expertise))

    async def _fail(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(mcp_tier2.RecordMeta, "create", _fail)

    with pytest.raises(RuntimeError, match="db unavailable"):
        await _record_expertise(
            {
                "domain": "infra",
                "type": "convention",
                "classification": "tactical",
                "content": "should not persist",
            },
            ctx(t.carlos, t.org, t.infra),
        )

    assert not (expertise / "infra.jsonl").exists() or "should not persist" not in (
        expertise / "infra.jsonl"
    ).read_text()
