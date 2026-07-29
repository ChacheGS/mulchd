"""Tests for project_cache.get_project_records — the per-domain, mtime-
validated cache in front of the full-corpus rescan it replaced."""

import json

from mulchd.mcp import project_cache


def _write_domain(expertise_dir, name, *records):
    expertise_dir.mkdir(parents=True, exist_ok=True)
    with (expertise_dir / f"{name}.jsonl").open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


async def test_returns_empty_list_when_expertise_dir_missing(tmp_path):
    result = await project_cache.get_project_records(tmp_path)
    assert result == []


async def test_reads_and_tags_records_with_domain(tmp_path):
    expertise_dir = tmp_path / "expertise"
    _write_domain(expertise_dir, "infra", {"id": "mx-1", "content": "a"})
    _write_domain(expertise_dir, "ops", {"id": "mx-2", "content": "b"})

    result = await project_cache.get_project_records(tmp_path)

    by_id = {r["id"]: r for r in result}
    assert by_id["mx-1"]["_domain"] == "infra"
    assert by_id["mx-2"]["_domain"] == "ops"


async def test_second_call_reuses_cache_when_nothing_changed(tmp_path, monkeypatch):
    expertise_dir = tmp_path / "expertise"
    _write_domain(expertise_dir, "infra", {"id": "mx-1", "content": "a"})

    await project_cache.get_project_records(tmp_path)

    calls = []
    original = project_cache.read_domain_records

    async def _counting(path):
        calls.append(path)
        return await original(path)

    monkeypatch.setattr(project_cache, "read_domain_records", _counting)

    await project_cache.get_project_records(tmp_path)

    assert calls == []


async def test_changed_domain_is_reparsed(tmp_path):
    expertise_dir = tmp_path / "expertise"
    _write_domain(expertise_dir, "infra", {"id": "mx-1", "content": "old"})
    await project_cache.get_project_records(tmp_path)

    # bump mtime forward so the change is guaranteed to register regardless
    # of filesystem mtime granularity
    path = expertise_dir / "infra.jsonl"
    _write_domain(expertise_dir, "infra", {"id": "mx-1", "content": "new"})
    import os

    new_mtime = path.stat().st_mtime + 2
    os.utime(path, (new_mtime, new_mtime))

    result = await project_cache.get_project_records(tmp_path)
    assert result[0]["content"] == "new"


async def test_new_domain_is_picked_up(tmp_path):
    expertise_dir = tmp_path / "expertise"
    _write_domain(expertise_dir, "infra", {"id": "mx-1", "content": "a"})
    await project_cache.get_project_records(tmp_path)

    _write_domain(expertise_dir, "ops", {"id": "mx-2", "content": "b"})
    result = await project_cache.get_project_records(tmp_path)

    assert {r["id"] for r in result} == {"mx-1", "mx-2"}


async def test_removed_domain_drops_out_of_result(tmp_path):
    expertise_dir = tmp_path / "expertise"
    _write_domain(expertise_dir, "infra", {"id": "mx-1", "content": "a"})
    _write_domain(expertise_dir, "ops", {"id": "mx-2", "content": "b"})
    await project_cache.get_project_records(tmp_path)

    (expertise_dir / "ops.jsonl").unlink()
    result = await project_cache.get_project_records(tmp_path)

    assert {r["id"] for r in result} == {"mx-1"}
