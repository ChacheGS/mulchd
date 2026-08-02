"""
Shared fixtures and helpers for tests/mcp/* — split out of the former
monolithic tests/test_mcp_tools.py.

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
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from mulchd.auth import AuthContext
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


def _make_fake_delete(expertise_dir: Path):
    """Return a delete_record stand-in that removes the record line from JSONL."""

    async def _fake(m_dir, domain, rid):
        path = expertise_dir / f"{domain}.jsonl"
        lines = [l for l in path.read_text().splitlines() if rid not in l]
        path.write_text("\n".join(lines) + ("\n" if lines else ""))

    return _fake


def _make_fake_move(expertise_dir: Path, incoming_references: list | None = None):
    """Return a move_record stand-in that relocates the record line between
    JSONL files, mirroring what `ml move` does on disk."""

    async def _fake(m_dir, source_domain, rid, target_domain):
        source_path = expertise_dir / f"{source_domain}.jsonl"
        lines = source_path.read_text().splitlines()
        moved = [l for l in lines if rid in l]
        kept = [l for l in lines if rid not in l]
        source_path.write_text("\n".join(kept) + ("\n" if kept else ""))
        target_path = expertise_dir / f"{target_domain}.jsonl"
        with target_path.open("a") as f:
            for line in moved:
                f.write(line + "\n")
        return {"success": True, "incomingReferences": incoming_references or []}

    return _fake


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
