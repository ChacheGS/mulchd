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
from typing import Any, cast

from .domains import validate_domain
from .records import Record as Record


class MulchError(Exception):
    pass


class RecordNotWrittenError(MulchError):
    """Raised by write_record when ml's own dedup logic skipped a duplicate
    or silently upserted an existing record in place, rather than creating a
    new one — not a failure of the `ml` call itself, but there's no new
    record object to return. Carries ml's raw summary dict so the caller can
    tell skipped (nothing changed) apart from updated (an existing record was
    just overwritten). See schemas.DEDUP_FIELD_BY_TYPE for which case each
    record type hits.
    """

    def __init__(self, summary: Record):
        self.summary = summary
        super().__init__(f"ml record did not create a new record: {summary}")


_ML_TIMEOUT_SECONDS = 30


async def _run(
    mulch_dir: Path, args: list[str], stdin_data: str | None = None
) -> dict[str, Any] | list[Any]:
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


async def write_record(mulch_dir: Path, domain: str, record: Record) -> Record:
    """
    Pipe `record` to `ml record {domain} --stdin --json`.
    Returns the written record dict (with id populated by mulch).

    Raises RecordNotWrittenError, not MulchError, when ml's dedup logic
    skipped or upserted instead of creating — that's ml behaving correctly,
    not a call failure. Callers should pre-check for a duplicate before
    calling this (see tier2._record_expertise); this exception is the
    backstop for the narrow race window between that check and this call.
    """
    validate_domain(domain)
    result = await _run(mulch_dir, ["record", domain, "--stdin"], stdin_data=json.dumps(record))
    if not isinstance(result, dict):
        raise MulchError(f"ml record returned an unexpected response: {result!r}")
    if result.get("created", 0) == 0:
        raise RecordNotWrittenError(result)
    # ml's --stdin mode returns a summary {success, created, ...} without the record object.
    # Fall back to reading the JSONL and matching on the fields we set.
    written = result.get("record") or _find_written_record(
        mulch_dir / "expertise" / f"{domain}.jsonl", record
    )
    if written is None:
        raise MulchError(f"ml record returned no record object: {result}")
    return written


def _find_written_record(jsonl_path: Path, record: Record) -> Record | None:
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
) -> list[Record]:
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
    records: list[Record] = []
    for domain, result in zip(domains, results):
        for entry in _extract_matches(result):
            entry["_domain"] = domain
            records.append(entry)
    return records


def _extract_matches(result: dict[str, Any] | list[Any]) -> list[Record]:
    if not isinstance(result, dict):
        return []
    matches: list[Record] = []
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


async def edit_record(mulch_dir: Path, domain: str, record_id: str, updates: Record) -> Record:
    """Edit a record via ml edit. Ownership check is the caller's responsibility."""
    args = ["edit", domain, record_id]
    for key, flag in _EDIT_FLAG_MAP.items():
        if key in updates:
            val = updates[key]
            if isinstance(val, list):
                val = ",".join(str(v) for v in cast(list[Any], val))
            args.extend([flag, str(val)])
    result = await _run(mulch_dir, args)
    return result if isinstance(result, dict) else {}


async def delete_record(mulch_dir: Path, domain: str, record_id: str) -> None:
    """Archive a record via ml archive (soft-delete). Ownership check is the caller's responsibility."""
    await _run(
        mulch_dir, ["archive", domain, "--records", record_id, "--reason", "deleted via MCP"]
    )


async def restore_record(mulch_dir: Path, record_id: str) -> Record:
    """Restore a soft-archived record via ml restore. Returns the restored record dict."""
    result = await _run(mulch_dir, ["restore", record_id])
    return result if isinstance(result, dict) else {}


async def move_record(
    mulch_dir: Path, source_domain: str, record_id: str, target_domain: str
) -> Record:
    """Move a record between domains via `ml move`, preserving its ID.

    Ignore this result's `incomingReferences` field — mulch 0.10.7's own
    computation of it skips the entire source-domain file (not just the
    moved record's line), so it misses same-domain references. Callers
    should compute inbound references themselves (see
    supersession.find_incoming_references) before calling this.

    Ownership check is the caller's responsibility."""
    result = await _run(mulch_dir, ["move", source_domain, record_id, target_domain])
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
) -> Record:
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
    result = await _run(mulch_dir, args)
    return result if isinstance(result, dict) else {}


async def audit_corpus(mulch_dir: Path, domain: str | None = None) -> dict[str, Any]:
    """Run `ml audit --json --suggest`, returning the full {report, suggestions}
    payload. mulchd does no analysis of its own — this is a pure pass-through
    to ml's existing corpus-quality report."""
    args = ["audit", "--suggest"]
    if domain:
        args += ["--domain", domain]
    result = await _run(mulch_dir, args)
    return result if isinstance(result, dict) else {}
