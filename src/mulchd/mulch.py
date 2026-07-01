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


_EDIT_FLAG_MAP: dict[str, str] = {
    "content": "--content",
    "name": "--name",
    "description": "--description",
    "resolution": "--resolution",
    "title": "--title",
    "rationale": "--rationale",
    "classification": "--classification",
    "files": "--files",
    "relates_to": "--relates-to",
    "supersedes": "--supersedes",
}


async def edit_record(mulch_dir: Path, domain: str, record_id: str, updates: dict) -> dict:
    """Edit a record via ml edit. Ownership check is the caller's responsibility."""
    args = ["edit", domain, record_id]
    for key, flag in _EDIT_FLAG_MAP.items():
        if key in updates:
            val = updates[key]
            if isinstance(val, list):
                val = ",".join(str(v) for v in val)
            args.extend([flag, str(val)])
    result = await _run(mulch_dir, args)
    return result if isinstance(result, dict) else {}


async def delete_record(mulch_dir: Path, domain: str, record_id: str) -> None:
    """Delete a single record via ml delete. Ownership check is the caller's responsibility."""
    await _run(mulch_dir, ["delete", domain, "--records", record_id])


async def ensure_domain(mulch_dir: Path, domain: str) -> None:
    """
    Bootstrap a project directory via `ml init` if it hasn't been initialised yet.
    After that, ml record handles adding new domains to mulch.config.yaml itself.
    """
    mulch_dir.parent.mkdir(parents=True, exist_ok=True)
    if not (mulch_dir / "mulch.config.yaml").exists():
        await _run(mulch_dir, ["init"], stdin_data=None)
