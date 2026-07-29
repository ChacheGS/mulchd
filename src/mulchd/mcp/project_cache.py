"""Per-project cache in front of the full-corpus record read.

_load_project_records used to reparse every domain's JSONL on every call
(cycle detection, cross-domain supersede tagging, and write/edit-time
reference validation all need the whole project's record set, not just
the current read scope). That's O(total corpus) work per call.

This module caches the parsed result per domain, keyed on the domain
file's mtime. Every call re-verifies against disk (a cheap stat() per
domain file) instead of trusting a write/edit/delete hook to invalidate
it — so it stays correct even when something outside this process (an
admin running `ml` directly) changes the files underneath it.

Known limitation: mtime granularity is filesystem-dependent (often 1
second) — a rewrite within the same second as a prior read could in
theory be missed. Writes here are human-driven (an MCP tool call, or an
admin manually running ml), not sub-second automation, so this is an
accepted risk rather than something engineered around.
"""

from pathlib import Path

from ..records import read_domain_records

_cache: dict[Path, dict[str, tuple[float, list[dict]]]] = {}


async def get_project_records(m_dir: Path) -> list[dict]:
    expertise_dir = m_dir / "expertise"
    if not expertise_dir.exists():
        _cache.pop(m_dir, None)
        return []

    domain_entry = _cache.setdefault(m_dir, {})
    current_files = {p.stem: p for p in expertise_dir.glob("*.jsonl")}

    for stale_domain in set(domain_entry) - set(current_files):
        del domain_entry[stale_domain]

    for domain, path in current_files.items():
        mtime = path.stat().st_mtime
        cached = domain_entry.get(domain)
        if cached is None or cached[0] != mtime:
            records = await read_domain_records(path)
            for r in records:
                r["_domain"] = domain
            domain_entry[domain] = (mtime, records)

    result: list[dict] = []
    for domain in current_files:
        result.extend(domain_entry[domain][1])
    return result
