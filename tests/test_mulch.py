"""
Tests for mulchd.mulch — calls audit_corpus directly (does not touch
mulchd.mcp.tier2), so this lives at the top level of tests/, not under
tests/mcp/.
"""

import shutil
from types import SimpleNamespace

import pytest

from mulchd.auth import AuthContext
from mulchd.mcp.tier2 import _record_expertise
from mulchd.models import (
    Organization,
    Project,
    Role,
    User,
    UserMembership,
)

ml_available = pytest.mark.skipif(
    not shutil.which("ml"), reason="ml not in PATH — run via: make test (or mise x -- uv run pytest)"
)


def ctx(user: User, org: Organization, project: Project, role: Role = Role.WRITER) -> AuthContext:
    return AuthContext(user=user, org=org, project=project, role=role)


@pytest.fixture
def data_path(tmp_path, monkeypatch):
    from mulchd.config import settings

    monkeypatch.setattr(settings, "data_path", tmp_path)
    return tmp_path


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


@ml_available
async def test_live_audit_corpus_returns_report_and_suggestions(team, data_path):
    """audit_corpus should shell out to the real ml audit --json --suggest and
    return the full {report, suggestions} payload for a real seeded corpus."""
    from mulchd.domains import mulch_dir
    from mulchd.mulch import audit_corpus

    t = team
    await _record_expertise(
        {
            "domain": "quality-test",
            "type": "convention",
            "classification": "tactical",
            "content": "Always enable S3 versioning on all buckets",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    result = await audit_corpus(mulch_dir("acme", "infra"))
    report = result["report"]
    assert report["total_records"] >= 1
    assert "quality-test" in report["domains"]
    assert "signals" in report
    assert "evidence_coverage" in report["signals"]
    assert "suggestions" in result
