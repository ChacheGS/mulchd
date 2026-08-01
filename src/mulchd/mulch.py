"""
Thin async wrapper around the `ml` CLI.

Writes go through `ml` so mulch handles validation, file locking, dedup,
ID generation, and hooks. Reads bypass the CLI — direct JSONL is faster
and the format is trivially simple.
"""

import asyncio
import json
import os
from enum import StrEnum
from pathlib import Path

from .domains import validate_domain


class MulchError(Exception):
    pass


_ML_TIMEOUT_SECONDS = 30


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
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(stdin_bytes), timeout=_ML_TIMEOUT_SECONDS
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise MulchError(f"ml {' '.join(args)} timed out after {_ML_TIMEOUT_SECONDS}s")

    if proc.returncode != 0:
        raw = stderr.decode().strip()
        try:
            msg = json.loads(raw).get("error", raw)
        except json.JSONDecodeError:
            msg = raw
        raise MulchError(msg)

    text = stdout.decode().strip()
    if not text:
        return {}
    return json.loads(text)


async def write_record(mulch_dir: Path, domain: str, record: dict) -> dict:
    """
    Pipe `record` to `ml record {domain} --stdin --json`.
    Returns the written record dict (with id populated by mulch).
    """
    validate_domain(domain)
    result = await _run(mulch_dir, ["record", domain, "--stdin"], stdin_data=json.dumps(record))
    # ml's --stdin mode returns a summary {success, created, ...} without the record object.
    # Fall back to reading the JSONL and matching on the fields we set.
    written = result.get("record") if isinstance(result, dict) else None
    if written is None and isinstance(result, dict) and result.get("created", 0) > 0:
        written = _find_written_record(mulch_dir / "expertise" / f"{domain}.jsonl", record)
    if written is None:
        raise MulchError(f"ml record returned no record object: {result}")
    return written


def _find_written_record(jsonl_path: Path, record: dict) -> dict | None:
    """Find a just-written record in the JSONL by matching stable fields."""
    try:
        lines = jsonl_path.read_text().splitlines()
    except OSError:
        return None
    # Match on fields we set ourselves — recorded_at + owner + type is unique enough.
    match_keys = {k: record[k] for k in ("recorded_at", "owner", "type") if k in record}
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if all(candidate.get(k) == v for k, v in match_keys.items()):
            return candidate
    return None


async def search_domains(
    mulch_dir: Path,
    query: str,
    domains: list[str] | None = None,
) -> list[dict]:
    """
    Run BM25 search via `ml --json search`.

    When `domains` is None, mulch searches all configured domains in one call.
    When specific domains are requested, we call once per domain with --domain,
    in parallel, and merge the results in `domains` order.
    """
    if not domains:
        result = await _run(mulch_dir, ["search", query])
        return _extract_matches(result)

    results = await asyncio.gather(
        *(_run(mulch_dir, ["search", query, "--domain", domain]) for domain in domains)
    )
    records: list[dict] = []
    for domain, result in zip(domains, results):
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
    """Archive a record via ml archive (soft-delete). Ownership check is the caller's responsibility."""
    await _run(
        mulch_dir, ["archive", domain, "--records", record_id, "--reason", "deleted via MCP"]
    )


async def restore_record(mulch_dir: Path, record_id: str) -> dict:
    """Restore a soft-archived record via ml restore. Returns the restored record dict."""
    result = await _run(mulch_dir, ["restore", record_id])
    return result if isinstance(result, dict) else {}


async def init_ml_project(mulch_dir: Path) -> None:
    """Bootstrap a project directory via `ml init` if not yet initialised."""
    mulch_dir.parent.mkdir(parents=True, exist_ok=True)
    if not (mulch_dir / "mulch.config.yaml").exists():
        await _run(mulch_dir, ["init"], stdin_data=None)


class OutcomeStatus(StrEnum):
    """Matches ml outcome --status's exact choices."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"


async def record_outcome(
    mulch_dir: Path,
    domain: str,
    record_id: str,
    status: OutcomeStatus,
    notes: str | None = None,
    agent: str | None = None,
) -> dict:
    """
    Append an outcome to an existing record via `ml outcome`. This feeds the
    confirmation-frequency boost ml's search already applies by default —
    mulchd previously never called this, so that boost had nothing to boost.

    `agent` identifies who confirmed this outcome — always the authenticated
    caller (see tier2._record_outcome), never a value the calling agent can
    set itself. Used to detect self-confirmation trust-laundering: someone
    editing a record's content then immediately confirming their own edit.
    """
    args = ["outcome", domain, record_id, "--status", status.value]
    if notes:
        args += ["--notes", notes]
    if agent:
        args += ["--agent", agent]
    return await _run(mulch_dir, args)


async def audit_corpus(mulch_dir: Path, domain: str | None = None) -> dict:
    """Run `ml audit --json --suggest`, returning the full {report, suggestions}
    payload. mulchd does no analysis of its own — this is a pure pass-through
    to ml's existing corpus-quality report."""
    args = ["audit", "--suggest"]
    if domain:
        args += ["--domain", domain]
    return await _run(mulch_dir, args)
