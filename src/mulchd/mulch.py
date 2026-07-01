"""
Thin async wrapper around the `ml` CLI.

Writes go through `ml` so mulch handles validation, file locking, dedup,
ID generation, and hooks. Reads bypass the CLI — direct JSONL is faster
and the format is trivially simple.
"""

import asyncio
import json
import os
from pathlib import Path


class MulchError(Exception):
    pass


async def _run(mulch_dir: Path, args: list[str], stdin_data: str | None = None) -> dict | list:
    env = {**os.environ, "MULCH_DIR": str(mulch_dir)}
    proc = await asyncio.create_subprocess_exec(
        "ml",
        "--json",
        *args,
        env=env,
        stdin=asyncio.subprocess.PIPE if stdin_data is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(mulch_dir.parent),
    )
    stdin_bytes = stdin_data.encode() if stdin_data is not None else None
    stdout, stderr = await proc.communicate(stdin_bytes)

    if proc.returncode != 0:
        raise MulchError(f"ml {' '.join(args)} exited {proc.returncode}: {stderr.decode().strip()}")

    text = stdout.decode().strip()
    if not text:
        return {}
    return json.loads(text)


async def write_record(mulch_dir: Path, domain: str, record: dict) -> dict:
    """
    Pipe `record` to `ml record {domain} --stdin --json`.
    Returns the written record dict (with id populated by mulch).
    """
    result = await _run(mulch_dir, ["record", domain, "--stdin"], stdin_data=json.dumps(record))
    # --json output: { success, command, action, domain, type, record, ... }
    written = result.get("record") if isinstance(result, dict) else None
    if written is None:
        raise MulchError(f"ml record returned no record object: {result}")
    return written


async def search_domains(
    mulch_dir: Path,
    query: str,
    domains: list[str] | None = None,
) -> list[dict]:
    """
    Run BM25 search via `ml --json search`.

    When `domains` is None, mulch searches all configured domains in one call.
    When specific domains are requested, we call once per domain with --domain
    and merge the results in the order returned.
    """
    if not domains:
        result = await _run(mulch_dir, ["search", query])
        return _extract_matches(result)

    records: list[dict] = []
    for domain in domains:
        result = await _run(mulch_dir, ["search", query, "--domain", domain])
        for entry in _extract_matches(result):
            entry["_domain"] = domain
            records.append(entry)
    return records


def _extract_matches(result: dict | list) -> list[dict]:
    if not isinstance(result, dict):
        return []
    matches: list[dict] = []
    for domain_entry in result.get("domains", []):
        domain = domain_entry.get("domain", "")
        for record in domain_entry.get("matches", []):
            record["_domain"] = domain
            matches.append(record)
    return matches


async def ensure_domain(mulch_dir: Path, domain: str) -> None:
    """
    Initialise the mulch store and domain if they don't exist yet.
    ml record auto-creates domains, but we may need ml init first.
    """
    expertise_dir = mulch_dir / "expertise"
    expertise_dir.mkdir(parents=True, exist_ok=True)
    config_path = mulch_dir / "mulch.config.yaml"
    if not config_path.exists():
        config_path.write_text(f"domains:\n  {domain}:\n    description: Auto-created by mulchd\n")
