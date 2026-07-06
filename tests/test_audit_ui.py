"""
Tests for /admin/audit — event log rendering and threat-model detection logic.

Strategy: seed RecordEvent, RecordEdit, RecordMeta, and JSONL files directly;
hit the page via admin_client and assert on HTML output.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mulchd.models import (
    Organization,
    Project,
    RecordEdit,
    RecordEvent,
    RecordMeta,
    Role,
    User,
    UserMembership,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup(tmp_path, monkeypatch):
    from mulchd.config import settings

    monkeypatch.setattr(settings, "data_path", tmp_path)
    org = await Organization.create(slug="acme", display_name="Acme")
    project = await Project.create(slug="platform", display_name="Platform", org=org)
    alice = await User.create(username="alice", display_name="Alice K.", token_hash="h1")
    bob = await User.create(username="bob", display_name="Bob M.", token_hash="h2")
    await UserMembership.create(user=alice, project=project, role=Role.WRITER)
    await UserMembership.create(user=bob, project=project, role=Role.WRITER)
    return org, project, alice, bob


def _jot(tmp_path: Path, domain: str, **fields) -> dict:
    expertise_dir = tmp_path / "acme" / "platform" / ".mulch" / "expertise"
    expertise_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "id": f"mx-{uuid.uuid4().hex[:8]}",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    with (expertise_dir / f"{domain}.jsonl").open("a") as f:
        f.write(json.dumps(record) + "\n")
    return record


# ---------------------------------------------------------------------------
# Basic rendering
# ---------------------------------------------------------------------------


async def test_audit_page_with_project_shows_events(admin_client, tmp_path, monkeypatch):
    """Selecting a project renders the event log with record IDs and action badges."""
    org, project, alice, bob = await _setup(tmp_path, monkeypatch)
    r = _jot(
        tmp_path,
        "api",
        type="convention",
        classification="tactical",
        content="Keep API keys out of logs",
        owner="alice",
    )
    await RecordMeta.create(
        record_id=r["id"],
        project=project,
        domain="api",
        author=alice,
        session_id=uuid.uuid4(),
        client="test",
    )
    await RecordEvent.create(
        record_id=r["id"],
        project=project,
        domain="api",
        actor=alice,
        action="write",
        client="test",
        session_id=uuid.uuid4(),
    )

    resp = await admin_client.get("/admin/audit?project=acme/platform")
    assert resp.status_code == 200
    assert r["id"] in resp.text
    assert "write" in resp.text
    assert "api" in resp.text


# ---------------------------------------------------------------------------
# F3 — cross-owner detection
# ---------------------------------------------------------------------------


async def test_audit_cross_owner_edit_shows_badge(admin_client, tmp_path, monkeypatch):
    """Edit by a non-original-author shows the amber cross-owner badge with display name."""
    org, project, alice, bob = await _setup(tmp_path, monkeypatch)
    r = _jot(
        tmp_path,
        "api",
        type="convention",
        classification="tactical",
        content="Original rule",
        owner="alice",
    )
    await RecordMeta.create(
        record_id=r["id"],
        project=project,
        domain="api",
        author=alice,
        session_id=uuid.uuid4(),
        client="test",
    )
    sid = uuid.uuid4()
    await RecordEvent.create(
        record_id=r["id"],
        project=project,
        domain="api",
        actor=bob,
        action="edit",
        client="test",
        session_id=sid,
    )
    await RecordEdit.create(
        record_id=r["id"],
        project=project,
        domain="api",
        actor=bob,
        before_snapshot={"content": "Original rule"},
        client="test",
        session_id=sid,
    )

    resp = await admin_client.get("/admin/audit?project=acme/platform")
    assert "cross-owner-badge" in resp.text
    assert "Alice K." in resp.text  # display name, not raw username


async def test_audit_same_owner_edit_no_badge(admin_client, tmp_path, monkeypatch):
    """Edit by the original author does not show the cross-owner badge."""
    org, project, alice, bob = await _setup(tmp_path, monkeypatch)
    r = _jot(
        tmp_path,
        "api",
        type="convention",
        classification="tactical",
        content="Alice's rule",
        owner="alice",
    )
    await RecordMeta.create(
        record_id=r["id"],
        project=project,
        domain="api",
        author=alice,
        session_id=uuid.uuid4(),
        client="test",
    )
    sid = uuid.uuid4()
    await RecordEvent.create(
        record_id=r["id"],
        project=project,
        domain="api",
        actor=alice,
        action="edit",
        client="test",
        session_id=sid,
    )
    await RecordEdit.create(
        record_id=r["id"],
        project=project,
        domain="api",
        actor=alice,
        before_snapshot={"content": "Alice's rule"},
        client="test",
        session_id=sid,
    )

    resp = await admin_client.get("/admin/audit?project=acme/platform")
    assert 'class="cross-owner-badge"' not in resp.text


async def test_audit_cross_owner_falls_back_to_jsonl_owner(admin_client, tmp_path, monkeypatch):
    """When RecordMeta has no entry, owner is resolved from the JSONL record's owner field."""
    org, project, alice, bob = await _setup(tmp_path, monkeypatch)
    r = _jot(
        tmp_path,
        "api",
        type="convention",
        classification="tactical",
        content="Old rule",
        owner="alice",
    )
    # No RecordMeta row — simulates a record pre-dating that table
    sid = uuid.uuid4()
    await RecordEvent.create(
        record_id=r["id"],
        project=project,
        domain="api",
        actor=bob,
        action="edit",
        client="test",
        session_id=sid,
    )
    await RecordEdit.create(
        record_id=r["id"],
        project=project,
        domain="api",
        actor=bob,
        before_snapshot={"content": "Old rule"},
        client="test",
        session_id=sid,
    )

    resp = await admin_client.get("/admin/audit?project=acme/platform")
    assert "cross-owner-badge" in resp.text


# ---------------------------------------------------------------------------
# F2 — classification downgrade detection
# ---------------------------------------------------------------------------


async def test_audit_write_superseding_foundational_with_lower_tier(
    admin_client, tmp_path, monkeypatch
):
    """Write that supersedes a foundational record with a lower tier shows 'foundational → tactical'."""
    org, project, alice, bob = await _setup(tmp_path, monkeypatch)
    original = _jot(
        tmp_path,
        "api",
        type="convention",
        classification="foundational",
        content="Guardrail",
        owner="alice",
    )
    new_rec = _jot(
        tmp_path,
        "api",
        type="convention",
        classification="tactical",
        content="Weakened",
        owner="bob",
        supersedes=[original["id"]],
    )
    await RecordEvent.create(
        record_id=new_rec["id"],
        project=project,
        domain="api",
        actor=bob,
        action="write",
        client="test",
        session_id=uuid.uuid4(),
    )

    resp = await admin_client.get("/admin/audit?project=acme/platform")
    assert "downgrade-badge" in resp.text
    assert "foundational → tactical" in resp.text


async def test_audit_write_superseding_foundational_same_tier(admin_client, tmp_path, monkeypatch):
    """Write superseding a foundational with same tier shows 'supersedes foundational' (not an arrow)."""
    org, project, alice, bob = await _setup(tmp_path, monkeypatch)
    original = _jot(
        tmp_path,
        "api",
        type="convention",
        classification="foundational",
        content="Guardrail",
        owner="alice",
    )
    new_rec = _jot(
        tmp_path,
        "api",
        type="convention",
        classification="foundational",
        content="Replacement guardrail",
        owner="bob",
        supersedes=[original["id"]],
    )
    await RecordEvent.create(
        record_id=new_rec["id"],
        project=project,
        domain="api",
        actor=bob,
        action="write",
        client="test",
        session_id=uuid.uuid4(),
    )

    resp = await admin_client.get("/admin/audit?project=acme/platform")
    assert "downgrade-badge" in resp.text
    assert "supersedes foundational" in resp.text
    assert "foundational → foundational" not in resp.text


async def test_audit_edit_that_lowers_classification(admin_client, tmp_path, monkeypatch):
    """Edit event where before_snapshot.classification was higher shows downgrade badge."""
    org, project, alice, bob = await _setup(tmp_path, monkeypatch)
    r = _jot(
        tmp_path,
        "api",
        type="convention",
        classification="tactical",
        content="Some rule",
        owner="alice",
    )
    sid = uuid.uuid4()
    await RecordEvent.create(
        record_id=r["id"],
        project=project,
        domain="api",
        actor=alice,
        action="edit",
        client="test",
        session_id=sid,
    )
    # before_snapshot shows it was foundational before the edit
    await RecordEdit.create(
        record_id=r["id"],
        project=project,
        domain="api",
        actor=alice,
        before_snapshot={"classification": "foundational"},
        client="test",
        session_id=sid,
    )

    resp = await admin_client.get("/admin/audit?project=acme/platform")
    assert "downgrade-badge" in resp.text
    assert "foundational → tactical" in resp.text


async def test_audit_tactical_supersedes_tactical_no_badge(admin_client, tmp_path, monkeypatch):
    """Superseding a tactical record with another tactical record shows no downgrade badge."""
    org, project, alice, bob = await _setup(tmp_path, monkeypatch)
    original = _jot(
        tmp_path,
        "api",
        type="convention",
        classification="tactical",
        content="Old approach",
        owner="alice",
    )
    new_rec = _jot(
        tmp_path,
        "api",
        type="convention",
        classification="tactical",
        content="New approach",
        owner="bob",
        supersedes=[original["id"]],
    )
    await RecordEvent.create(
        record_id=new_rec["id"],
        project=project,
        domain="api",
        actor=bob,
        action="write",
        client="test",
        session_id=uuid.uuid4(),
    )

    resp = await admin_client.get("/admin/audit?project=acme/platform")
    assert 'class="downgrade-badge"' not in resp.text


# ---------------------------------------------------------------------------
# Restore action
# ---------------------------------------------------------------------------


async def test_audit_restore_redirects(admin_client, tmp_path, monkeypatch):
    """POST /audit/restore calls restore_record and redirects back to the audit page."""
    from mulchd.config import settings

    monkeypatch.setattr(settings, "data_path", tmp_path)

    import mulchd.admin.audit as audit_mod

    calls: list[tuple] = []

    async def _fake_restore(m_dir, record_id):
        calls.append((m_dir, record_id))

    monkeypatch.setattr(audit_mod, "restore_record", _fake_restore)

    resp = await admin_client.post(
        "/admin/audit/restore",
        data={"project": "acme/platform", "record_id": "mx-abc123"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "acme/platform" in resp.headers["location"]
    assert len(calls) == 1
    assert calls[0][1] == "mx-abc123"
