"""
write_record / write_* dispatch tool tests.
"""

import json
import uuid
from pathlib import Path

import pytest

from mulchd.domains import list_available_domains
from mulchd.mcp.context import auth_ctx
from mulchd.mcp.schemas import TIER2_TOOLS
from mulchd.mcp.tier2 import _read_expertise, _record_expertise, call_tool
from mulchd.models import RecordMeta, Role, UserMembership
from mulchd.mulch import MulchError
from tests.mcp.conftest import _jot, _make_fake_delete, ctx, ml_available


def _tool_by_name(name):
    return next(t for t in TIER2_TOOLS if t.name == name)


def test_edit_record_schema_does_not_advertise_evidence():
    """evidence is write-only (set at record creation, not editable later) —
    edit_record's schema must not promise a field its handler silently drops."""
    edit_record = _tool_by_name("edit_record")
    assert "evidence" not in edit_record.input_schema["properties"]


def test_write_tools_schemas_advertise_evidence():
    for name in (
        "write_convention",
        "write_decision",
        "write_failure",
        "write_pattern",
        "write_reference",
        "write_guide",
    ):
        tool = _tool_by_name(name)
        assert "evidence" in tool.input_schema["properties"], name


def test_write_convention_schema_rejects_unknown_evidence_field():
    """evidence's additionalProperties: false must reject unrecognized keys —
    ml's own evidence schema is equally closed, so an unknown key should be
    caught by the MCP SDK's schema validation (which runs before dispatch,
    see call_tool's default validate_input=True) rather than surfacing later
    as an ml write failure."""
    import jsonschema

    tool = _tool_by_name("write_convention")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance={
                "domain": "infra",
                "classification": "tactical",
                "content": "x",
                "evidence": {"not_a_real_field": "oops"},
            },
            schema=tool.input_schema,
        )


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
    # Names the org/project so an agent juggling multiple mulchd connections
    # can catch a wrong-target write.
    assert "acme/infra" in result[0].text


async def test_write_convention_with_evidence(team, data_path, fake_write_record):
    """evidence (commit hash, issue/PR reference, etc.) must flow through into
    the written record, not get silently dropped."""
    t = team
    await _record_expertise(
        {
            "domain": "infra",
            "type": "convention",
            "classification": "tactical",
            "content": "Use IMDSv2 on all EC2 instances",
            "evidence": {"commit": "abc1234", "gh": "org/repo#42"},
        },
        ctx(t.carlos, t.org, t.infra),
    )

    _, structured = await _read_expertise({"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra))

    record = structured["records"][0]
    assert record["evidence"] == {"commit": "abc1234", "gh": "org/repo#42"}


async def test_write_convention_with_evidence_array_values_joined(
    team, data_path, fake_write_record
):
    """mulchd accepts multiple PRs/tickets/etc per evidence field (an ergonomic
    mulchd extends beyond ml's own scalar-only evidence schema), but ml itself
    only accepts a single string per field — so arrays must be joined into one
    string before the record is handed to ml."""
    t = team
    await _record_expertise(
        {
            "domain": "infra",
            "type": "convention",
            "classification": "tactical",
            "content": "Rotate creds quarterly",
            "evidence": {
                "gh": ["org/repo#42", "org/repo#43"],
                "linear": ["TKT-1", "TKT-2", "TKT-3"],
            },
        },
        ctx(t.carlos, t.org, t.infra),
    )

    _, structured = await _read_expertise({"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra))

    record = structured["records"][0]
    assert record["evidence"] == {
        "gh": "org/repo#42, org/repo#43",
        "linear": "TKT-1, TKT-2, TKT-3",
    }


async def test_write_record_evidence_is_optional(team, data_path, fake_write_record):
    """Omitting evidence entirely must not break the write (existing behavior,
    guards against the new field becoming accidentally required)."""
    t = team
    result = await _record_expertise(
        {
            "domain": "infra",
            "type": "convention",
            "classification": "tactical",
            "content": "No evidence here",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    assert len(result) == 1

    _, structured = await _read_expertise({"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra))
    assert "evidence" not in structured["records"][0]


async def test_write_decision_dispatch_creates_decision_record(team, data_path, fake_write_record):
    """The write_decision tool call must inject type='decision' before reaching
    _record_expertise, without the caller having to pass type explicitly."""
    from mcp.types import CallToolRequestParams

    t = team
    token = auth_ctx.set(ctx(t.carlos, t.org, t.infra))
    try:
        result = await call_tool(
            None,
            CallToolRequestParams(
                name="write_decision",
                arguments={
                    "domain": "infra",
                    "classification": "tactical",
                    "title": "Use IMDSv2",
                    "rationale": "Blocks SSRF-based credential theft",
                },
            ),
        )
    finally:
        auth_ctx.reset(token)
    assert result.is_error is False
    assert "decision" in result.content[0].text

    text_content, _ = await _read_expertise({"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra))
    assert "IMDSv2" in text_content[0].text


async def test_write_convention_dispatch_rejects_missing_content(
    team, data_path, fake_write_record
):
    """write_convention must still enforce its required field via the shared
    validation in _record_expertise even though the schema itself has no
    'type' property for the caller to get wrong."""
    from mcp.types import CallToolRequestParams

    t = team
    token = auth_ctx.set(ctx(t.carlos, t.org, t.infra))
    try:
        result = await call_tool(
            None,
            CallToolRequestParams(
                name="write_convention",
                arguments={"domain": "infra", "classification": "tactical"},
            ),
        )
    finally:
        auth_ctx.reset(token)
    assert result.is_error is True
    assert "requires: content" in result.content[0].text


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


@pytest.mark.parametrize("files_value", [[], ["src/foo.py"]], ids=["empty", "populated"])
async def test_write_decision_rejects_files_regardless_of_content(
    team, data_path, fake_write_record, files_value
):
    """`files` is only valid on pattern/reference records — ml's own schema
    rejects it on decision (and convention/failure/guide) whether the list is
    empty or populated, with an error that never mentions `files` at all. This
    must be caught before ever reaching ml, for both cases identically."""
    t = team
    with pytest.raises(ValueError, match="record type 'decision' does not support 'files'"):
        await _record_expertise(
            {
                "domain": "infra",
                "type": "decision",
                "classification": "tactical",
                "title": "some decision",
                "rationale": "some rationale",
                "files": files_value,
            },
            ctx(t.carlos, t.org, t.infra),
        )


async def test_write_pattern_accepts_files(team, data_path, fake_write_record):
    """The one case files= is actually meant for — must still work."""
    t = team
    result = await _record_expertise(
        {
            "domain": "infra",
            "type": "pattern",
            "classification": "tactical",
            "name": "retry wrapper",
            "description": "wraps flaky calls with exponential backoff",
            "files": ["src/retry.py"],
        },
        ctx(t.carlos, t.org, t.infra),
    )
    assert "Recorded" in result[0].text or "mx-" in result[0].text


async def test_edit_record_rejects_files_on_unsupported_type(team, data_path, fake_write_record):
    """The same files/type restriction applies on the edit path, checked
    against the existing record's actual type rather than a `type` arg (edit
    doesn't take one)."""
    from mulchd.mcp.tier2 import _edit_record

    t = team
    await _record_expertise(
        {
            "domain": "infra",
            "type": "convention",
            "classification": "tactical",
            "content": "always do the thing",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    records = await _read_expertise({"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra))
    record_id = records[1]["records"][0]["id"]

    with pytest.raises(ValueError, match="record type 'convention' does not support 'files'"):
        await _edit_record(
            {"record_id": record_id, "domain": "infra", "files": ["src/foo.py"]},
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


@ml_available
async def test_live_write_convention_duplicate_does_not_crash(team, data_path):
    """Regression test for the reported crash: writing a convention whose
    content exactly matches an existing one used to raise MulchError('ml
    record returned no record object') because ml skips the duplicate
    (created=0) and the old wrapper only ever checked created>0. Runs
    against the real ml binary, not a mock, since the bug was in how
    mulchd interpreted ml's actual response shape."""
    t = team
    args = {
        "domain": "live-dup-test",
        "type": "convention",
        "classification": "tactical",
        "content": "Always enable S3 versioning on all buckets",
    }
    await _record_expertise(args, ctx(t.carlos, t.org, t.infra))

    result = await _record_expertise(dict(args), ctx(t.carlos, t.org, t.infra))
    assert "Not recorded" in result[0].text


@ml_available
async def test_live_write_decision_duplicate_title_does_not_crash(team, data_path):
    """Same regression, for the 'updated' (upsert) branch that write_decision/
    write_pattern/write_reference/write_guide hit instead of 'skipped' —
    ml silently overwrites the existing record (updated=0 -> created stays 0),
    which the old wrapper also didn't handle."""
    t = team
    await _record_expertise(
        {
            "domain": "live-dup-test2",
            "type": "decision",
            "classification": "tactical",
            "title": "Use Aurora Serverless",
            "rationale": "v1",
        },
        ctx(t.carlos, t.org, t.infra),
    )

    result = await _record_expertise(
        {
            "domain": "live-dup-test2",
            "type": "decision",
            "classification": "tactical",
            "title": "Use Aurora Serverless",
            "rationale": "v2 attempted overwrite",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    assert "Not recorded" in result[0].text


async def test_write_convention_exact_duplicate_content_rejected_gracefully(
    team, data_path, fake_write_record
):
    """Writing a convention with content matching an existing one returns a
    plain rejection message instead of crashing — ml's own dedup logic
    silently skips convention/failure duplicates rather than creating them,
    and the old wrapper unconditionally assumed a new record was created."""
    t = team
    args = {
        "domain": "infra",
        "type": "convention",
        "classification": "tactical",
        "content": "Always enable S3 versioning",
    }
    await _record_expertise(args, ctx(t.carlos, t.org, t.infra))

    result = await _record_expertise(dict(args), ctx(t.carlos, t.org, t.infra))
    assert "Not recorded" in result[0].text
    assert "already exists" in result[0].text

    text_content, structured = await _read_expertise(
        {"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra)
    )
    assert len(structured["records"]) == 1


async def test_write_decision_duplicate_title_rejected_gracefully(
    team, data_path, fake_write_record
):
    """Writing a decision with a title matching an existing one is also
    rejected — ml's own dedup logic would silently overwrite (upsert) the
    existing decision in place rather than skip, which is worse than a
    no-op, so this must never be allowed to reach ml at all."""
    t = team
    await _record_expertise(
        {
            "domain": "infra",
            "type": "decision",
            "classification": "tactical",
            "title": "Use Postgres",
            "rationale": "v1",
        },
        ctx(t.carlos, t.org, t.infra),
    )

    result = await _record_expertise(
        {
            "domain": "infra",
            "type": "decision",
            "classification": "tactical",
            "title": "Use Postgres",
            "rationale": "v2 — this must not silently overwrite v1",
        },
        ctx(t.jorge, t.org, t.infra),
    )
    assert "Not recorded" in result[0].text
    assert "already exists" in result[0].text

    text_content, structured = await _read_expertise(
        {"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra)
    )
    assert len(structured["records"]) == 1
    assert structured["records"][0]["rationale"] == "v1"


async def test_write_convention_same_content_different_domain_rejected_gracefully(
    team, data_path, fake_write_record
):
    """ml's own dedup key and record-ID key are the same field for every
    built-in type, and ID generation has no notion of domain — so writing the
    same convention content to a second domain in the same project would make
    ml independently mint the identical record ID there. ml's own dedup check
    only looks within one domain's file and would happily create it as a
    second, unrelated record, but mulchd's RecordMeta requires record_id to be
    unique per project. This must be caught before ever reaching ml."""
    t = team
    await _record_expertise(
        {
            "domain": "infra",
            "type": "convention",
            "classification": "tactical",
            "content": "Always enable S3 versioning",
        },
        ctx(t.carlos, t.org, t.infra),
    )

    result = await _record_expertise(
        {
            "domain": "security",
            "type": "convention",
            "classification": "tactical",
            "content": "Always enable S3 versioning",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    assert "Not recorded" in result[0].text
    assert "already exists" in result[0].text
    assert "infra" in result[0].text
    # The existing record is in a different domain than the one being written
    # to — edit_record/supersedes would point at someone else's record, so the
    # remedy must be "rename", not those.
    assert "rename" in result[0].text.lower()
    assert "edit_record to update it, or add supersedes" not in result[0].text

    domains = await list_available_domains(t.org.slug, t.infra.slug)
    assert not any(d["name"] == "security" for d in domains)


async def test_write_convention_record_id_collision_rolls_back_on_race(
    team, data_path, fake_write_record, monkeypatch
):
    """Regression test for a reported crash: two near-simultaneous writes to
    different domains can both pass the pre-check (it reads project state
    before ml runs) and both succeed at the ml layer, but the second
    RecordMeta.create() then hits a real Postgres unique constraint violation
    on (project, record_id). This must roll back the JSONL write and return a
    graceful message instead of surfacing the raw IntegrityError."""
    t = team
    m_dir = data_path / t.org.slug / t.infra.slug / ".mulch"
    (m_dir / "expertise").mkdir(parents=True, exist_ok=True)

    collided_id = "mx-abc123"
    await RecordMeta.create(
        record_id=collided_id,
        project=t.infra,
        domain="infra",
        author=t.carlos,
        session_id=uuid.uuid4(),
        client="test",
    )

    import mulchd.mcp.tier2 as mcp_tier2

    async def _write_colliding(m_dir: Path, domain: str, record: dict) -> dict:
        expertise_dir = m_dir / "expertise"
        expertise_dir.mkdir(parents=True, exist_ok=True)
        result = {"id": collided_id, **record}
        with (expertise_dir / f"{domain}.jsonl").open("a") as f:
            f.write(json.dumps(result) + "\n")
        return result

    monkeypatch.setattr(mcp_tier2, "write_record", _write_colliding)
    monkeypatch.setattr(mcp_tier2, "delete_record", _make_fake_delete(m_dir / "expertise"))

    result = await _record_expertise(
        {
            "domain": "networking",
            "type": "convention",
            "classification": "tactical",
            "content": "Use private subnets for databases",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    assert "Not recorded" in result[0].text

    domain_file = m_dir / "expertise" / "networking.jsonl"
    assert not domain_file.exists() or domain_file.read_text().strip() == ""
    assert await RecordMeta.filter(project=t.infra, record_id=collided_id).count() == 1


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
    with pytest.raises(
        ValueError, match="supersedes references records that don't exist: mx-ghost"
    ):
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


async def test_record_expertise_accepts_valid_cross_domain_supersedes(
    team, data_path, fake_write_record
):
    """A supersedes target in a different domain is accepted — cross-domain
    supersession is a supported, designed-for case."""
    from mulchd.mcp.tier2 import _record_expertise

    t = team
    old = _jot(
        data_path,
        "acme",
        "infra",
        "guardrails",
        type="convention",
        classification="foundational",
        content="Old",
        owner="carlos",
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


async def test_record_expertise_rejects_archived_supersedes_target(
    team, data_path, fake_write_record
):
    """A supersedes target that's been archived (soft-deleted) is rejected the
    same as a fabricated ID — it's no longer live."""
    from mulchd.domains import mulch_dir
    from mulchd.mcp.tier2 import _record_expertise

    t = team
    m_dir = mulch_dir("acme", "infra")
    archive_dir = m_dir / "archive"
    archive_dir.mkdir(parents=True)
    (archive_dir / "infra.jsonl").write_text(
        json.dumps({"id": "mx-archived1", "type": "convention", "classification": "tactical"})
        + "\n"
    )
    with pytest.raises(
        ValueError, match="supersedes references records that don't exist: mx-archived1"
    ):
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


async def test_write_rolls_back_jsonl_when_db_metadata_fails(
    team, data_path, fake_write_record, monkeypatch
):
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

    assert (
        not (expertise / "infra.jsonl").exists()
        or "should not persist" not in (expertise / "infra.jsonl").read_text()
    )


async def test_write_rejects_unknown_domain_when_strict(
    team, data_path, fake_write_record, monkeypatch
):
    monkeypatch.setenv("MULCHD_POLICY_STRICT_DOMAINS", "true")
    t = team

    with pytest.raises(ValueError, match="does not exist"):
        await _record_expertise(
            {
                "domain": "never-created",
                "type": "convention",
                "classification": "tactical",
                "content": "x",
            },
            ctx(t.carlos, t.org, t.infra),
        )


async def test_write_strict_names_the_closest_existing_domain(
    team, data_path, fake_write_record, monkeypatch
):
    t = team
    # Create the baseline domain before strict mode is enabled — strict_domains
    # blocks writes to any not-yet-existing domain, so it must not be on yet
    # for this seeding write, or it would be rejected before we ever reach the
    # typo-detection path this test is actually exercising.
    await _record_expertise(
        {
            "domain": "architecture",
            "type": "convention",
            "classification": "tactical",
            "content": "x",
        },
        ctx(t.carlos, t.org, t.infra),
    )

    monkeypatch.setenv("MULCHD_POLICY_STRICT_DOMAINS", "true")
    with pytest.raises(ValueError, match="did you mean the existing domain 'architecture'"):
        await _record_expertise(
            {
                "domain": "architecutre",
                "type": "convention",
                "classification": "tactical",
                "content": "y",
            },
            ctx(t.carlos, t.org, t.infra),
        )


async def test_write_still_auto_creates_when_not_strict(team, data_path, fake_write_record):
    """Unaffected by this change when the policy is left at its default."""
    t = team
    result = await _record_expertise(
        {"domain": "brand-new", "type": "convention", "classification": "tactical", "content": "x"},
        ctx(t.carlos, t.org, t.infra),
    )
    assert "Recorded" in result[0].text


def test_write_tools_schemas_mention_strict_domains_caveat():
    for name in (
        "write_convention",
        "write_decision",
        "write_failure",
        "write_pattern",
        "write_reference",
        "write_guide",
    ):
        tool = _tool_by_name(name)
        assert "strict domain creation" in (tool.description or "").lower()


async def test_write_supersession_warning_blocks_when_enforced(
    team, data_path, fake_write_record, monkeypatch
):
    monkeypatch.setenv("MULCHD_POLICY_GUARDRAIL_ENFORCEMENT", "enforce")
    t = team
    foundational = await _record_expertise(
        {
            "domain": "infra",
            "type": "decision",
            "classification": "foundational",
            "title": "Old guardrail",
            "rationale": "x",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    import re

    old_id = re.search(r"\(mx-[a-f0-9]+\)", foundational[0].text).group(0)[1:-1]

    result = await _record_expertise(
        {
            "domain": "infra",
            "type": "decision",
            "classification": "tactical",
            "title": "New approach",
            "rationale": "y",
            "supersedes": [old_id],
        },
        ctx(t.carlos, t.org, t.infra),
    )
    assert "Not completed" in result[0].text
    assert "SUPERSESSION WARNING" in result[0].text
    assert "confirm=true" in result[0].text

    # No record was actually written.
    _, structured = await _read_expertise({"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra))
    assert len(structured["records"]) == 1


async def test_write_confirm_true_proceeds_when_enforced(
    team, data_path, fake_write_record, monkeypatch
):
    monkeypatch.setenv("MULCHD_POLICY_GUARDRAIL_ENFORCEMENT", "enforce")
    t = team
    foundational = await _record_expertise(
        {
            "domain": "infra",
            "type": "decision",
            "classification": "foundational",
            "title": "Old guardrail",
            "rationale": "x",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    import re

    old_id = re.search(r"\(mx-[a-f0-9]+\)", foundational[0].text).group(0)[1:-1]

    result = await _record_expertise(
        {
            "domain": "infra",
            "type": "decision",
            "classification": "tactical",
            "title": "New approach",
            "rationale": "y",
            "supersedes": [old_id],
            "confirm": True,
        },
        ctx(t.carlos, t.org, t.infra),
    )
    assert "Recorded" in result[0].text
    assert "SUPERSESSION WARNING" in result[0].text  # still shown, for audit visibility


async def test_gate_guardrail_warnings_uses_elicitation_when_client_supports_it(
    team, data_path, monkeypatch
):
    """When the connected client declared the elicitation capability,
    _gate_guardrail_warnings must ask it in real time rather than falling
    back to confirm=true — and a decline must block, distinctly from the
    confirm=true rejection message."""
    monkeypatch.setenv("MULCHD_POLICY_GUARDRAIL_ENFORCEMENT", "enforce")
    from mcp.types import ClientCapabilities, ElicitResult

    from mulchd.mcp.tier2 import _gate_guardrail_warnings

    t = team

    class FakeSession:
        client_capabilities = ClientCapabilities(elicitation={})
        elicit_calls: list[tuple[str, dict]] = []

        async def elicit_form(self, message, requested_schema):
            self.elicit_calls.append((message, requested_schema))
            return ElicitResult(action="decline")

    class FakeCtx:
        session = FakeSession()

    fake_ctx = FakeCtx()
    rejection = await _gate_guardrail_warnings(
        t.infra, fake_ctx, ["\n\n⚠ SUPERSESSION WARNING: test"], False
    )
    assert rejection is not None
    assert "Not completed" in rejection
    assert "declined via elicitation" in rejection
    assert "SUPERSESSION WARNING" in rejection
    assert fake_ctx.session.elicit_calls
    message, schema = fake_ctx.session.elicit_calls[0]
    assert "SUPERSESSION WARNING" in message
    assert schema == {"type": "object", "properties": {}}


async def test_gate_guardrail_warnings_elicitation_accept_proceeds(team, data_path, monkeypatch):
    monkeypatch.setenv("MULCHD_POLICY_GUARDRAIL_ENFORCEMENT", "enforce")
    from mcp.types import ClientCapabilities, ElicitResult

    from mulchd.mcp.tier2 import _gate_guardrail_warnings

    t = team

    class FakeSession:
        client_capabilities = ClientCapabilities(elicitation={})

        async def elicit_form(self, message, requested_schema):
            return ElicitResult(action="accept")

    class FakeCtx:
        session = FakeSession()

    rejection = await _gate_guardrail_warnings(
        t.infra, FakeCtx(), ["\n\n⚠ SUPERSESSION WARNING: test"], False
    )
    assert rejection is None


async def test_write_supersession_warning_not_blocked_when_warn_mode(
    team, data_path, fake_write_record
):
    """Default policy value (warn) preserves today's behavior exactly."""
    t = team
    foundational = await _record_expertise(
        {
            "domain": "infra",
            "type": "decision",
            "classification": "foundational",
            "title": "Old guardrail",
            "rationale": "x",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    import re

    old_id = re.search(r"\(mx-[a-f0-9]+\)", foundational[0].text).group(0)[1:-1]

    result = await _record_expertise(
        {
            "domain": "infra",
            "type": "decision",
            "classification": "tactical",
            "title": "New approach",
            "rationale": "y",
            "supersedes": [old_id],
        },
        ctx(t.carlos, t.org, t.infra),
    )
    assert "Recorded" in result[0].text
    assert "SUPERSESSION WARNING" in result[0].text
