"""
Integration tests for MCP tool handlers.

Strategy:
  - write_record (ml CLI) is monkeypatched for _record_expertise tests so no
    external binary is required.
  - read_records, get_recent, list_domains read JSONL directly, so we
    seed files with _jot() and test without any mocking.
  - search_records is omitted: it shells out to `ml search` (BM25) which
    requires the mulch CLI to be installed.

Isolation model: path-based — data_path/org/project/.mulch/expertise/domain.jsonl
Each project has its own file tree; the tests confirm that read paths respect
ctx.project.slug and no cross-project leakage is possible via a wrong context.
"""

import json
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from mulchd.auth import AuthContext
from mulchd.domains import list_available_domains
from mulchd.mcp.tier2 import (
    _get_recent,
    _list_domains,
    _read_expertise,
    _record_expertise,
)
from mulchd.models import (
    Organization,
    Project,
    RecordEdit,
    RecordEvent,
    Role,
    User,
    UserMembership,
)
from mulchd.mulch import MulchError

ml_available = pytest.mark.skipif(
    not shutil.which("ml"), reason="ml not in PATH — run via: mise x -- uv run pytest"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def ctx(user: User, org: Organization, project: Project, role: Role = Role.WRITER) -> AuthContext:
    return AuthContext(user=user, org=org, project=project, role=role)


def _jot(
    data_path: Path,
    org_slug: str,
    proj_slug: str,
    domain: str,
    *,
    recorded_at: datetime | None = None,
    **fields,
) -> dict:
    """Write a record directly to JSONL, bypassing the ml CLI."""
    expertise_dir = data_path / org_slug / proj_slug / ".mulch" / "expertise"
    expertise_dir.mkdir(parents=True, exist_ok=True)
    ts = (recorded_at or datetime.now(timezone.utc)).isoformat()
    record = {"id": f"mx-{uuid.uuid4().hex[:8]}", "recorded_at": ts, **fields}
    with (expertise_dir / f"{domain}.jsonl").open("a") as f:
        f.write(json.dumps(record) + "\n")
    return record


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def data_path(tmp_path, monkeypatch):
    from mulchd.config import settings

    monkeypatch.setattr(settings, "data_path", tmp_path)
    return tmp_path


@pytest.fixture
def fake_write_record(monkeypatch, data_path):
    """Replace ml CLI calls with direct JSONL writes for _record_expertise tests."""
    import mulchd.mcp.tier2 as mcp_tier2

    async def _write(m_dir: Path, domain: str, record: dict) -> dict:
        expertise_dir = m_dir / "expertise"
        expertise_dir.mkdir(parents=True, exist_ok=True)
        result = {"id": f"mx-{uuid.uuid4().hex[:8]}", **record}
        with (expertise_dir / f"{domain}.jsonl").open("a") as f:
            f.write(json.dumps(result) + "\n")
        return result

    async def _init(m_dir: Path) -> None:
        (m_dir / "expertise").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(mcp_tier2, "write_record", _write)
    monkeypatch.setattr(mcp_tier2, "init_ml_project", _init)


@pytest.fixture
async def team(db, data_path):
    """
    org: acme
    projects:
      infra        — carlos (writer), jorge (writer)
      data-platform — jorge (writer), ana (writer)
    """
    org = await Organization.create(slug="acme", display_name="Acme Corp")
    infra = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    data_proj = await Project.create(slug="data-platform", display_name="Data Platform", org=org)

    carlos = await User.create(username="carlos", display_name="Carlos G.", token_hash="h1")
    jorge = await User.create(username="jorge", display_name="Jorge M.", token_hash="h2")
    ana = await User.create(username="ana", display_name="Ana R.", token_hash="h3")

    await UserMembership.create(user=carlos, project=infra, role=Role.WRITER)
    await UserMembership.create(user=jorge, project=infra, role=Role.WRITER)
    await UserMembership.create(user=jorge, project=data_proj, role=Role.WRITER)
    await UserMembership.create(user=ana, project=data_proj, role=Role.WRITER)

    return SimpleNamespace(
        org=org,
        infra=infra,
        data=data_proj,
        carlos=carlos,
        jorge=jorge,
        ana=ana,
    )


# ---------------------------------------------------------------------------
# Cross-project isolation — reads
# ---------------------------------------------------------------------------


async def test_read_isolation_different_projects(team, data_path):
    """Records written to infra are invisible when reading from data-platform."""
    t = team
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="decision",
        classification="foundational",
        content="Use Terraform for all infra",
        owner="carlos",
    )

    # Member of both projects reading from infra sees the record.
    text_content, structured = await _read_expertise(
        {"domains": ["infra"]}, ctx(t.jorge, t.org, t.infra)
    )
    assert "Terraform" in text_content[0].text

    # Same user reading from data-platform sees nothing.
    text_content, structured = await _read_expertise(
        {"domains": ["infra"]}, ctx(t.jorge, t.org, t.data)
    )
    assert "Terraform" not in text_content[0].text
    assert "No records found" in text_content[0].text


async def test_get_recent_isolation_different_projects(team, data_path):
    """get_recent respects project boundaries even when both projects share an org."""
    t = team
    since = datetime.now(timezone.utc) - timedelta(seconds=1)

    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="foundational",
        content="VPCs use /16 CIDR blocks",
        owner="carlos",
    )

    result = await _get_recent(
        {"since": since.isoformat(), "domains": ["infra"]},
        ctx(t.jorge, t.org, t.infra),
    )
    assert "VPCs use /16 CIDR blocks" in result[0].text

    result = await _get_recent(
        {"since": since.isoformat(), "domains": ["infra"]},
        ctx(t.jorge, t.org, t.data),
    )
    assert "VPCs use /16 CIDR blocks" not in result[0].text
    assert "No records" in result[0].text


async def test_list_domains_isolation_different_projects(team, data_path):
    """list_domains record counts are per-project, not shared."""
    t = team
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="foundational",
        content="r1",
        owner="carlos",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="decision",
        classification="foundational",
        content="r2",
        owner="jorge",
    )

    # infra project: 2 records in the infra domain
    text_content, structured = await _list_domains(ctx(t.carlos, t.org, t.infra))
    assert "2 records" in text_content[0].text

    # data-platform project: no expertise files at all → no domains listed
    text_content, structured = await _list_domains(ctx(t.jorge, t.org, t.data))
    assert "infra" not in text_content[0].text


# ---------------------------------------------------------------------------
# Cross-user knowledge recovery — same project, different user
# ---------------------------------------------------------------------------


async def test_cross_user_read_sees_all_project_records(team, data_path):
    """All project members see records regardless of who wrote them."""
    t = team
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="failure",
        classification="foundational",
        content="NAT gateway quota exhaustion caused prod outage",
        owner="carlos",
    )

    # jorge reads and sees carlos's record with author attribution
    text_content, structured = await _read_expertise(
        {"domains": ["infra"]}, ctx(t.jorge, t.org, t.infra)
    )
    assert "NAT gateway quota exhaustion" in text_content[0].text
    assert "carlos" in text_content[0].text


async def test_multiple_authors_all_visible_to_team(team, data_path):
    """Records from multiple authors are all visible to every project member."""
    t = team
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="decision",
        classification="foundational",
        content="Prefer Aurora Serverless for managed DBs",
        owner="carlos",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="Tag all resources with team and cost-centre",
        owner="jorge",
    )

    # ana is not in infra, but carlos is — carlos sees both records
    text_content, structured = await _read_expertise(
        {"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra)
    )
    text = text_content[0].text
    assert "Aurora Serverless" in text
    assert "Tag all resources" in text
    assert "carlos" in text
    assert "jorge" in text


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


# ---------------------------------------------------------------------------
# Role enforcement
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# get_recent — timestamp filtering
# ---------------------------------------------------------------------------


async def test_get_recent_excludes_old_records(team, data_path):
    """Records written before `since` are excluded; newer ones appear."""
    t = team
    old_ts = datetime.now(timezone.utc) - timedelta(hours=2)
    new_ts = datetime.now(timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)

    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="observational",
        content="Old practice — now superseded",
        owner="carlos",
        recorded_at=old_ts,
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="decision",
        classification="foundational",
        content="New decision post-migration",
        owner="jorge",
        recorded_at=new_ts,
    )

    result = await _get_recent(
        {"since": cutoff.isoformat(), "domains": ["infra"]},
        ctx(t.jorge, t.org, t.infra),
    )
    text = result[0].text
    assert "New decision post-migration" in text
    assert "Old practice" not in text


async def test_get_recent_multiple_domains(team, data_path):
    """get_recent aggregates across domains when multiple are specified."""
    t = team
    since = datetime.now(timezone.utc) - timedelta(seconds=1)

    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="decision",
        classification="foundational",
        content="Infra domain record",
        owner="carlos",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "governance",
        type="convention",
        classification="foundational",
        content="Governance domain record",
        owner="jorge",
    )

    result = await _get_recent(
        {"since": since.isoformat(), "domains": ["infra", "governance"]},
        ctx(t.carlos, t.org, t.infra),
    )
    text = result[0].text
    assert "Infra domain record" in text
    assert "Governance domain record" in text


# ---------------------------------------------------------------------------
# list_domains — record counts and display
# ---------------------------------------------------------------------------


async def test_list_domains_shows_org_and_project_name(team, data_path):
    t = team
    text_content, structured = await _list_domains(ctx(t.carlos, t.org, t.infra))
    assert "Acme Corp" in text_content[0].text
    assert "Infrastructure" in text_content[0].text


async def test_list_domains_counts_match_written_records(team, data_path):
    t = team
    for _ in range(3):
        _jot(
            data_path,
            "acme",
            "infra",
            "infra",
            type="convention",
            classification="observational",
            content="record",
            owner="carlos",
        )

    text_content, structured = await _list_domains(ctx(t.carlos, t.org, t.infra))
    assert "3 records" in text_content[0].text


# ---------------------------------------------------------------------------
# New tests: validation, unknown-domain warnings, structured truncation
# ---------------------------------------------------------------------------


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


async def test_read_records_unknown_domain_warns(team, data_path):
    """read_records warns on unknown domains rather than silently returning empty."""
    t = team
    text_content, structured = await _read_expertise(
        {"domains": ["nonexistent-domain"]},
        ctx(t.carlos, t.org, t.infra),
    )
    assert "Unknown domain" in text_content[0].text
    assert "nonexistent-domain" in text_content[0].text


async def test_read_records_cursor_pagination(team, data_path):
    """Cursor-based pagination returns pages in recorded_at order with an opaque next_cursor."""
    import base64

    t = team
    for i in range(3):
        _jot(
            data_path,
            "acme",
            "infra",
            "infra",
            type="convention",
            classification="tactical",
            content=f"record {i}",
            owner="carlos",
            recorded_at=datetime(2026, 1, 1, i, 0, 0, tzinfo=timezone.utc),
        )

    _, s1 = await _read_expertise({"domains": ["infra"], "limit": 2}, ctx(t.carlos, t.org, t.infra))
    assert len(s1["records"]) == 2
    assert s1["truncated"] is True
    assert s1["next_cursor"] is not None
    # cursor must be opaque — not a raw ISO timestamp
    assert s1["next_cursor"] != s1["records"][-1].get("recorded_at")
    # must be valid base64
    base64.b64decode(s1["next_cursor"])
    assert s1["records"][0]["content"] == "record 0"
    assert s1["records"][1]["content"] == "record 1"

    _, s2 = await _read_expertise(
        {"domains": ["infra"], "limit": 2, "cursor": s1["next_cursor"]},
        ctx(t.carlos, t.org, t.infra),
    )
    assert len(s2["records"]) == 1
    assert s2["records"][0]["content"] == "record 2"
    assert s2["truncated"] is False
    assert s2["next_cursor"] is None


async def test_read_records_cursor_tiebreak_on_id(team, data_path):
    """Two records with identical timestamps are disambiguated by id so no record is skipped."""
    t = team
    ts = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="twin a",
        owner="carlos",
        recorded_at=ts,
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="twin b",
        owner="carlos",
        recorded_at=ts,
    )

    _, s1 = await _read_expertise({"domains": ["infra"], "limit": 1}, ctx(t.carlos, t.org, t.infra))
    assert s1["truncated"] is True

    _, s2 = await _read_expertise(
        {"domains": ["infra"], "limit": 1, "cursor": s1["next_cursor"]},
        ctx(t.carlos, t.org, t.infra),
    )
    assert len(s2["records"]) == 1
    # both records returned across two pages — no skip, no duplicate
    contents = {s1["records"][0]["content"], s2["records"][0]["content"]}
    assert contents == {"twin a", "twin b"}


async def test_read_records_structured_truncation_flag(team, data_path):
    """read_records sets truncated=True when limit is hit."""
    t = team
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="record one",
        owner="carlos",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="record two",
        owner="carlos",
    )

    text_content, structured = await _read_expertise(
        {"domains": ["infra"], "limit": 1},
        ctx(t.carlos, t.org, t.infra),
    )
    assert structured["truncated"] is True
    assert len(structured["records"]) == 1

    text_content2, structured2 = await _read_expertise(
        {"domains": ["infra"], "limit": 10},
        ctx(t.carlos, t.org, t.infra),
    )
    assert structured2["truncated"] is False


# ---------------------------------------------------------------------------
# Regression tests — cross-evaluation findings (2026-07-03)
# ---------------------------------------------------------------------------


# Critical: write_record broken due to owner_display in ml payload
# ----------------------------------------------------------------


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


# High: domain orphaned when ml write fails
# ------------------------------------------


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


# Medium: list_domains structured output missing self-documenting fields
# -----------------------------------------------------------------------


async def test_list_domains_structured_includes_get_recent_hint(team, data_path):
    """list_domains structured output should carry the get_recent hint so clients
    consuming structured content don't lose the session-start instruction."""
    t = team
    _, structured = await _list_domains(ctx(t.carlos, t.org, t.infra))
    assert (
        "get_recent_hint" in structured or "hint" in structured
    ), "structured output must include the get_recent timestamp hint"


async def test_list_domains_structured_includes_domain_uri(team, data_path, fake_write_record):
    """Each domain entry should carry its resource URI so agents don't have to
    hand-construct mulchd://domain/<name> or make a separate list_resources call."""
    t = team
    await _record_expertise(
        {
            "domain": "infra",
            "type": "convention",
            "classification": "tactical",
            "content": "Use IMDSv2 on all EC2 instances",
        },
        ctx(t.carlos, t.org, t.infra),
    )

    _, structured = await _list_domains(ctx(t.carlos, t.org, t.infra))
    assert structured["domains"], "expected at least one domain after writing a record"
    for d in structured["domains"]:
        assert d["uri"] == f"mulchd://domain/{d['name']}"


async def test_list_domains_structured_includes_language(team, data_path):
    """list_domains structured output should expose knowledge_language when set,
    so clients using structured content still receive the translation directive."""
    t = team
    t.infra.knowledge_language = "es"
    await t.infra.save()

    _, structured = await _list_domains(ctx(t.carlos, t.org, t.infra))
    assert structured.get("language") == "es"


# Medium: unknown domain not signalled in structured output (§5)
# ---------------------------------------------------------------


async def test_read_records_unknown_domain_in_structured_output(team, data_path):
    """read_records should expose unknown domain names in structured output,
    not just as a text warning that structured clients may never see."""
    t = team
    _, structured = await _read_expertise(
        {"domains": ["does-not-exist"]},
        ctx(t.carlos, t.org, t.infra),
    )
    assert (
        "unknown_domains" in structured
    ), "structured output must include 'unknown_domains' when unrecognised names are requested"
    assert "does-not-exist" in structured["unknown_domains"]


# Superseded record marking
# -------------------------


async def test_read_records_marks_superseded(team, data_path):
    """When record B supersedes record A, A should be marked in text and structured output."""
    t = team
    old = _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="foundational",
        content="Old approach",
        owner="carlos",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="foundational",
        content="New approach",
        owner="carlos",
        supersedes=[old["id"]],
    )

    text_content, structured = await _read_expertise(
        {"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra)
    )
    new_record = next(r for r in structured["records"] if r.get("supersedes"))
    assert "superseded" in text_content[0].text
    assert new_record["id"] in text_content[0].text  # superseded_by ID appears in text
    superseded_records = [r for r in structured["records"] if r.get("_superseded")]
    assert len(superseded_records) == 1
    assert superseded_records[0]["id"] == old["id"]
    assert superseded_records[0]["_superseded_by"] == new_record["id"]


async def test_non_superseded_records_not_marked(team, data_path):
    """Records not referenced in any supersedes list should not be marked."""
    t = team
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="foundational",
        content="Standalone convention",
        owner="carlos",
    )

    text_content, structured = await _read_expertise(
        {"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra)
    )
    assert "superseded" not in text_content[0].text
    assert not any(r.get("_superseded") for r in structured["records"])


async def test_superseded_marked_when_superseder_in_other_domain(team, data_path):
    """A record is marked superseded even when the superseding record lives in a different domain."""
    t = team
    old = _jot(
        data_path,
        "acme",
        "infra",
        "guardrails",
        type="convention",
        classification="foundational",
        content="Old guardrail",
        owner="carlos",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "policies",
        type="convention",
        classification="foundational",
        content="Replacement rule",
        owner="carlos",
        supersedes=[old["id"]],
    )

    # Read only the victim's domain — superseder is not in the result set
    _, structured = await _read_expertise(
        {"domains": ["guardrails"]}, ctx(t.carlos, t.org, t.infra)
    )
    records = structured["records"]
    assert len(records) == 1
    assert records[0]["_superseded"] is True
    assert records[0]["_superseded_by"] is not None


async def test_superseded_marked_when_superseder_not_in_query_results(team, data_path):
    """Same-domain supersession: victim is marked even when the superseder didn't match the query."""
    t = team
    old = _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="foundational",
        content="Old approach",
        owner="carlos",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="foundational",
        content="New approach",
        owner="jorge",
        supersedes=[old["id"]],
    )

    # Reading only carlos's records — superseder (jorge's) is filtered out
    _, structured = await _read_expertise({"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra))
    # Both records come back (no owner filter on read_records), but confirm
    # the old one is marked regardless of whether we'd have filtered the new one
    old_record = next(r for r in structured["records"] if r["id"] == old["id"])
    assert old_record["_superseded"] is True


# delete_record auto-cleanup
# --------------------------


def _make_fake_delete(expertise_dir: Path):
    """Return a delete_record stand-in that removes the record line from JSONL."""

    async def _fake(m_dir, domain, rid):
        path = expertise_dir / f"{domain}.jsonl"
        lines = [l for l in path.read_text().splitlines() if rid not in l]
        path.write_text("\n".join(lines) + ("\n" if lines else ""))

    return _fake


async def test_delete_last_record_removes_domain(team, data_path, monkeypatch):
    """Deleting the last record in a domain removes the domain JSONL automatically."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _delete_record

    t = team
    expertise = data_path / "acme" / "infra" / ".mulch" / "expertise"
    record = _jot(
        data_path,
        "acme",
        "infra",
        "scratch",
        type="convention",
        classification="foundational",
        content="only record",
        owner="carlos",
    )
    monkeypatch.setattr(mcp_tier2, "delete_record", _make_fake_delete(expertise))

    await _delete_record(
        {"record_id": record["id"], "domain": "scratch"}, ctx(t.carlos, t.org, t.infra)
    )
    assert not (expertise / "scratch.jsonl").exists()


async def test_delete_non_last_record_preserves_domain(team, data_path, monkeypatch):
    """Deleting one of several records leaves the domain intact."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _delete_record

    t = team
    expertise = data_path / "acme" / "infra" / ".mulch" / "expertise"
    r1 = _jot(
        data_path,
        "acme",
        "infra",
        "keep",
        type="convention",
        classification="foundational",
        content="first",
        owner="carlos",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "keep",
        type="convention",
        classification="foundational",
        content="second",
        owner="carlos",
    )
    monkeypatch.setattr(mcp_tier2, "delete_record", _make_fake_delete(expertise))

    await _delete_record({"record_id": r1["id"], "domain": "keep"}, ctx(t.carlos, t.org, t.infra))
    assert (expertise / "keep.jsonl").exists()


# RecordEvent audit trail (data layer — not exposed via MCP)
# ----------------------------------------------------------


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


async def test_edit_record_snapshots_before_values(team, data_path, fake_write_record):
    """RecordEdit captures the pre-edit values of changed fields."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _edit_record
    from mulchd.models import RecordEdit

    t = team

    await mcp_tier2._record_expertise(
        {
            "domain": "snap-test",
            "type": "convention",
            "classification": "tactical",
            "content": "original",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    records = await mcp_tier2._read_expertise(
        {"domains": ["snap-test"]}, ctx(t.carlos, t.org, t.infra)
    )
    record_id = records[1]["records"][0]["id"]

    async def _noop_edit(m_dir, domain, rid, updates):
        pass

    orig_edit = mcp_tier2.edit_record
    mcp_tier2.edit_record = _noop_edit
    await _edit_record(
        {"record_id": record_id, "domain": "snap-test", "content": "updated"},
        ctx(t.carlos, t.org, t.infra),
    )
    mcp_tier2.edit_record = orig_edit

    edit = await RecordEdit.filter(record_id=record_id).first()
    assert edit is not None
    assert edit.before_snapshot == {"content": "original"}


# ---------------------------------------------------------------------------
# Classification enum and supersession/downgrade detection
# ---------------------------------------------------------------------------


async def test_supersede_alerts_foundational_same_tier(team, data_path):
    """_supersede_alerts fires when a foundational record is superseded, even at the same tier."""
    from mulchd.domains import mulch_dir
    from mulchd.mcp.tier2 import _supersede_alerts

    t = team
    r = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="convention",
        classification="foundational",
        content="Guardrail",
        owner="carlos",
    )
    alerts = await _supersede_alerts(mulch_dir("acme", "infra"), [r["id"]], "foundational")
    assert r["id"] in alerts
    assert alerts[r["id"]] == "foundational"


async def test_supersede_alerts_tier_downgrade(team, data_path):
    """_supersede_alerts fires when a lower tier supersedes a higher one."""
    from mulchd.domains import mulch_dir
    from mulchd.mcp.tier2 import _supersede_alerts

    t = team
    r = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="convention",
        classification="tactical",
        content="Tactical rule",
        owner="carlos",
    )
    alerts = await _supersede_alerts(mulch_dir("acme", "infra"), [r["id"]], "observational")
    assert r["id"] in alerts


async def test_supersede_alerts_no_alert_same_nonfoundational_tier(team, data_path):
    """_supersede_alerts does not fire when tactical supersedes tactical."""
    from mulchd.domains import mulch_dir
    from mulchd.mcp.tier2 import _supersede_alerts

    t = team
    r = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="convention",
        classification="tactical",
        content="Tactical rule",
        owner="carlos",
    )
    alerts = await _supersede_alerts(mulch_dir("acme", "infra"), [r["id"]], "tactical")
    assert r["id"] not in alerts


async def test_annotate_edits_sets_edited_flag(team, data_path):
    """_annotate_edits marks records that have RecordEdit rows with _edited and edit count."""
    from mulchd.mcp.tier2 import _annotate_edits

    t = team
    r = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="convention",
        classification="tactical",
        content="Some rule",
        owner="carlos",
    )
    await RecordEdit.create(
        record_id=r["id"],
        project=t.infra,
        domain="api",
        actor=t.carlos,
        before_snapshot={"content": "Old rule"},
        client="test",
        session_id=uuid.uuid4(),
    )
    records = [r.copy()]
    await _annotate_edits(records, t.infra.id)
    assert records[0].get("_edited") is True
    assert records[0].get("_edit_count") == 1
    assert records[0].get("_last_edited_by") == "Carlos G."


async def test_annotate_edits_counts_multiple_edits(team, data_path):
    """_annotate_edits counts each edit and records the last editor."""
    from mulchd.mcp.tier2 import _annotate_edits

    t = team
    r = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="convention",
        classification="tactical",
        content="v1",
        owner="carlos",
    )
    for _ in range(3):
        await RecordEdit.create(
            record_id=r["id"],
            project=t.infra,
            domain="api",
            actor=t.jorge,
            before_snapshot={"content": "v1"},
            client="test",
            session_id=uuid.uuid4(),
        )
    records = [r.copy()]
    await _annotate_edits(records, t.infra.id)
    assert records[0]["_edit_count"] == 3
    assert records[0]["_last_edited_by"] == "Jorge M."


async def test_supersedes_foundational_annotated_on_superseder(team, data_path):
    """_mark_superseded annotates _supersedes_foundational on the superseding record."""
    from mulchd.mcp.tier2 import _mark_superseded

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
    superseder = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="convention",
        classification="tactical",
        content="Weakened rule",
        owner="jorge",
        supersedes=[original["id"]],
    )
    original["_domain"] = "api"
    superseder["_domain"] = "api"

    records = [original, superseder]
    await _mark_superseded(records, "acme", "infra")

    assert records[0].get("_superseded") is True
    assert records[1].get("_supersedes_foundational") == [original["id"]]


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


async def test_edit_record_classification_downgrade_warning(team, data_path, fake_write_record):
    """edit_record response includes CLASSIFICATION DOWNGRADE when classification is lowered."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _edit_record

    t = team

    await mcp_tier2._record_expertise(
        {"domain": "api", "type": "convention", "classification": "foundational", "content": "v1"},
        ctx(t.carlos, t.org, t.infra),
    )
    records = await mcp_tier2._read_expertise({"domains": ["api"]}, ctx(t.carlos, t.org, t.infra))
    record_id = records[1]["records"][0]["id"]

    async def _noop_edit(m_dir, domain, rid, updates):
        pass

    orig_edit = mcp_tier2.edit_record
    mcp_tier2.edit_record = _noop_edit
    result = await _edit_record(
        {"record_id": record_id, "domain": "api", "classification": "tactical"},
        ctx(t.carlos, t.org, t.infra),
    )
    mcp_tier2.edit_record = orig_edit

    assert "CLASSIFICATION DOWNGRADE" in result[0].text
    assert "foundational" in result[0].text
    assert "tactical" in result[0].text


async def test_cross_domain_hints_in_read_records(team, data_path):
    """read_records includes cross_domain_hints when a record is superseded from another domain."""
    t = team
    victim = _jot(
        data_path,
        "acme",
        "infra",
        "guardrails",
        type="convention",
        classification="foundational",
        content="Original guardrail",
        owner="carlos",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "policies",
        type="convention",
        classification="foundational",
        content="Replacement",
        owner="carlos",
        supersedes=[victim["id"]],
    )

    # Read only the victim's domain
    _, structured = await _read_expertise(
        {"domains": ["guardrails"]}, ctx(t.carlos, t.org, t.infra)
    )
    hints = structured.get("cross_domain_hints", [])
    assert len(hints) == 1
    assert hints[0]["record_id"] == victim["id"]
    assert hints[0]["in_domain"] == "policies"
