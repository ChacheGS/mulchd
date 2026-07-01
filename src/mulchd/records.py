"""
Read expertise records directly from JSONL files.

Writes and search go through server.mulch (ml CLI subprocess).
Direct reads are used for read_expertise and get_recent, where we load
all records for a domain without ranking — no BM25 needed there.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


async def read_domain_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            records.append(json.loads(stripped))
        except json.JSONDecodeError:
            pass
    return records


async def get_file_mod_time(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except FileNotFoundError:
        return None
