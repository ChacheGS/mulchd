"""
delete_record tests — domain auto-cleanup.
"""

import json

import pytest

from tests.mcp.conftest import ctx, _jot, _make_fake_delete


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


async def test_delete_rolls_back_jsonl_when_db_event_fails(team, data_path, monkeypatch):
    """If the RecordEvent row fails after the JSONL delete already succeeded, the
    record must be restored so the operation fails cleanly instead of leaving a
    deleted-but-untracked record with no history."""
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

    async def _fake_restore(m_dir, record_id):
        path = expertise / "scratch.jsonl"
        path.write_text(json.dumps(record) + "\n")
        return record

    monkeypatch.setattr(mcp_tier2, "restore_record", _fake_restore)

    async def _fail(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(mcp_tier2.RecordEvent, "create", _fail)

    with pytest.raises(RuntimeError, match="db unavailable"):
        await _delete_record(
            {"record_id": record["id"], "domain": "scratch"}, ctx(t.carlos, t.org, t.infra)
        )

    lines = (expertise / "scratch.jsonl").read_text().splitlines()
    assert any(record["id"] in line for line in lines)
