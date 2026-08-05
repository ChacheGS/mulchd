"""Per-project cache in front of full-corpus JSONL scans.

The old tier2 helpers this replaces (_load_project_records, then later
_load_archived_ids) used to reparse every file in expertise/ or archive/ on
every call — cycle detection, cross-domain supersede tagging, and
write/edit-time reference validation all need the whole project's record
set, not just the current read scope. That's O(total corpus) work per call.

This module caches the parsed result per file, keyed on that file's mtime.
Every call re-verifies against disk (a cheap stat() per file) instead of
trusting a write/edit/delete hook to invalidate it — so it stays correct
even when something outside this process (an admin running `ml` directly)
changes the files underneath it.

Known limitation: mtime granularity is filesystem-dependent (often 1
second) — a rewrite within the same second as a prior read could in
theory be missed. Writes here are human-driven (an MCP tool call, or an
admin manually running ml), not sub-second automation, so this is an
accepted risk rather than something engineered around.
"""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

from ..mulch import Record
from ..records import read_domain_records

_T = TypeVar("_T")


async def _scan_cached_dir(
    cache: dict[Path, dict[str, tuple[float, _T]]],
    dir_path: Path,
    parse: Callable[[Path], Awaitable[_T]],
) -> dict[str, _T]:
    """Glob dir_path for *.jsonl, reparsing only files whose mtime changed
    since the last scan of this directory, and dropping any that vanished.
    Returns {file_stem: parsed_value} for every file currently on disk.

    Shared by get_project_records and get_archived_ids — both need the same
    mtime-diffing walk, differing only in what `parse` extracts per file."""
    if not dir_path.exists():
        cache.pop(dir_path, None)
        return {}

    file_entry = cache.setdefault(dir_path, {})
    current_files = {p.stem: p for p in dir_path.glob("*.jsonl")}

    for stale in set(file_entry) - set(current_files):
        del file_entry[stale]

    for name, path in current_files.items():
        mtime = path.stat().st_mtime
        cached = file_entry.get(name)
        if cached is None or cached[0] != mtime:
            file_entry[name] = (mtime, await parse(path))

    return {name: file_entry[name][1] for name in current_files}


_project_cache: dict[Path, dict[str, tuple[float, list[Record]]]] = {}


async def get_project_records(m_dir: Path) -> list[Record]:
    async def _parse(path: Path) -> list[Record]:
        records = await read_domain_records(path)
        for r in records:
            r["_domain"] = path.stem
        return records

    per_domain = await _scan_cached_dir(_project_cache, m_dir / "expertise", _parse)
    result: list[Record] = []
    for records in per_domain.values():
        result.extend(records)
    return result


_archive_cache: dict[Path, dict[str, tuple[float, set[str]]]] = {}


async def get_archived_ids(m_dir: Path) -> set[str]:
    """IDs of soft-deleted (archived) records — stored under archive/,
    outside the live expertise/ tree get_project_records reads."""

    async def _parse(path: Path) -> set[str]:
        records = await read_domain_records(path)
        return {r["id"] for r in records if r.get("id")}

    per_file = await _scan_cached_dir(_archive_cache, m_dir / "archive", _parse)
    ids: set[str] = set()
    for file_ids in per_file.values():
        ids |= file_ids
    return ids
