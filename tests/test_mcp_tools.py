"""
Integration tests for MCP tool handlers.

Strategy:
  - write_record (ml CLI) is monkeypatched for _record_expertise tests so no
    external binary is required.
  - _read_expertise, _get_recent, _list_domains read JSONL directly, so we
    seed files with _jot() and test without any mocking.
  - _search_expertise is omitted: it shells out to `ml search` (BM25) which
    requires the mulch CLI to be installed.

Isolation model: path-based — data_path/org/project/.mulch/expertise/domain.jsonl
Each project has its own file tree; the tests confirm that read paths respect
ctx.project.slug and no cross-project leakage is possible via a wrong context.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from mulchd.auth import AuthContext
from mulchd.models import Organization, Project, Role, User, UserMembership
from mulchd.mcp.tier3 import _get_recent, _list_domains, _read_expertise, _record_expertise

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
    import mulchd.mcp.tier3 as mcp_tier3

    async def _write(m_dir: Path, domain: str, record: dict) -> dict:
        expertise_dir = m_dir / "expertise"
        expertise_dir.mkdir(parents=True, exist_ok=True)
        result = {"id": f"mx-{uuid.uuid4().hex[:8]}", **record}
        with (expertise_dir / f"{domain}.jsonl").open("a") as f:
            f.write(json.dumps(result) + "\n")
        return result

    async def _ensure(m_dir: Path, domain: str) -> None:
        (m_dir / "expertise").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(mcp_tier3, "write_record", _write)
    monkeypatch.setattr(mcp_tier3, "ensure_domain", _ensure)


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
    data_proj = await Project.create(
        slug="data-platform", display_name="Data Platform", org=org
    )

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
    result = await _read_expertise({"domains": ["infra"]}, ctx(t.jorge, t.org, t.infra))
    assert "Terraform" in result[0].text

    # Same user reading from data-platform sees nothing.
    result = await _read_expertise({"domains": ["infra"]}, ctx(t.jorge, t.org, t.data))
    assert "Terraform" not in result[0].text
    assert "No records found" in result[0].text


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
    assert "No records found" in result[0].text


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
    [result] = await _list_domains(ctx(t.carlos, t.org, t.infra))
    assert "2 records" in result.text

    # data-platform project: no expertise files at all → no domains listed
    [result] = await _list_domains(ctx(t.jorge, t.org, t.data))
    assert "infra" not in result.text


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
    result = await _read_expertise({"domains": ["infra"]}, ctx(t.jorge, t.org, t.infra))
    assert "NAT gateway quota exhaustion" in result[0].text
    assert "carlos" in result[0].text


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
    result = await _read_expertise({"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra))
    text = result[0].text
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
            "content": {"content": "Use IMDSv2 on all EC2 instances"},
        },
        ctx(t.jorge, t.org, t.infra),
    )

    result = await _read_expertise({"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra))
    assert "IMDSv2" in result[0].text
    assert "jorge" in result[0].text


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
                "content": {"content": "test"},
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
            "content": {"content": "Always enable S3 versioning"},
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
    [result] = await _list_domains(ctx(t.carlos, t.org, t.infra))
    assert "Acme Corp" in result.text
    assert "Infrastructure" in result.text


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

    [result] = await _list_domains(ctx(t.carlos, t.org, t.infra))
    assert "3 records" in result.text
