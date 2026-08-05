"""
Tests for mulchd.mulch — the ml CLI wrapper module. Lives at the top level of
tests/, not under tests/mcp/, since mulch.py isn't part of the mcp package.
"""

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from mulchd.auth import AuthContext
from mulchd.mcp.tier2 import _record_expertise
from mulchd.models import (
    Organization,
    Project,
    Role,
    User,
    UserMembership,
)

ml_available = pytest.mark.skipif(
    not shutil.which("ml"),
    reason="ml not in PATH — run via: make test (or mise x -- uv run pytest)",
)


def ctx(user: User, org: Organization, project: Project, role: Role = Role.WRITER) -> AuthContext:
    return AuthContext(user=user, org=org, project=project, role=role)


@pytest.fixture
def data_path(tmp_path, monkeypatch):
    from mulchd.config import settings

    monkeypatch.setattr(settings, "data_path", tmp_path)
    return tmp_path


@pytest.fixture
async def team(db, data_path):
    """
    org: acme
    projects:
      infra        — carlos (writer), jorge (writer)
      data-platform — jorge (writer), ana (writer)
    """
    org = await Organization.create(slug="acme", display_name="Acme Corp")
    infra = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    data_proj = await Project.create(slug="data-platform", display_name="Data Platform", org=org)

    carlos = await User.create(username="carlos", display_name="Carlos G.", token_hash="h1")
    jorge = await User.create(username="jorge", display_name="Jorge M.", token_hash="h2")
    ana = await User.create(username="ana", display_name="Ana R.", token_hash="h3")

    await UserMembership.create(user=carlos, project=infra, role=Role.WRITER)
    await UserMembership.create(user=jorge, project=infra, role=Role.WRITER)
    await UserMembership.create(user=jorge, project=data_proj, role=Role.WRITER)
    await UserMembership.create(user=ana, project=data_proj, role=Role.WRITER)

    return SimpleNamespace(
        org=org,
        infra=infra,
        data=data_proj,
        carlos=carlos,
        jorge=jorge,
        ana=ana,
    )


@ml_available
async def test_live_audit_corpus_returns_report_and_suggestions(team, data_path):
    """audit_corpus should shell out to the real ml audit --json --suggest and
    return the full {report, suggestions} payload for a real seeded corpus."""
    from mulchd.domains import mulch_dir
    from mulchd.mulch import audit_corpus

    t = team
    await _record_expertise(
        {
            "domain": "quality-test",
            "type": "convention",
            "classification": "tactical",
            "content": "Always enable S3 versioning on all buckets",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    result = await audit_corpus(mulch_dir("acme", "infra"))
    report = result["report"]
    assert report["total_records"] >= 1
    assert "quality-test" in report["domains"]
    assert "signals" in report
    assert "evidence_coverage" in report["signals"]
    assert "suggestions" in result


@ml_available
async def test_live_audit_corpus_with_domain_filter(team, data_path):
    """The --domain flag should scope the report to just that domain."""
    from mulchd.domains import mulch_dir
    from mulchd.mulch import audit_corpus

    t = team
    await _record_expertise(
        {
            "domain": "scoped-a",
            "type": "convention",
            "classification": "tactical",
            "content": "rule a",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    await _record_expertise(
        {
            "domain": "scoped-b",
            "type": "convention",
            "classification": "tactical",
            "content": "rule b",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    result = await audit_corpus(mulch_dir("acme", "infra"), domain="scoped-a")
    report = result["report"]
    assert report["domains"] == ["scoped-a"]


# ---------------------------------------------------------------------------
# _run — error handling (pure logic, no real ml needed)
# ---------------------------------------------------------------------------


class _FakeProc:
    def __init__(self, returncode, stdout=b"", stderr=b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self.killed = False

    async def communicate(self, stdin_bytes):
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True

    async def wait(self):
        return self.returncode


async def test_run_kills_process_and_raises_on_timeout(monkeypatch, tmp_path):
    import mulchd.mulch as mulch_module
    from mulchd.mulch import MulchError, _run

    proc = _FakeProc(0)

    async def _fake_create_subprocess_exec(*args, **kwargs):
        return proc

    async def _fake_wait_for(coro, timeout):
        coro.close()
        raise TimeoutError

    monkeypatch.setattr(
        mulch_module.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec
    )
    monkeypatch.setattr(mulch_module.asyncio, "wait_for", _fake_wait_for)

    with pytest.raises(MulchError, match="timed out"):
        await _run(tmp_path, ["search", "query"])

    assert proc.killed


async def test_run_raises_mulch_error_with_json_stderr(monkeypatch, tmp_path):
    import mulchd.mulch as mulch_module
    from mulchd.mulch import MulchError, _run

    async def _fake_create_subprocess_exec(*args, **kwargs):
        return _FakeProc(1, stderr=b'{"error": "domain not found"}')

    monkeypatch.setattr(
        mulch_module.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec
    )

    with pytest.raises(MulchError, match="domain not found"):
        await _run(tmp_path, ["search", "query"])


async def test_run_raises_mulch_error_with_non_json_stderr(monkeypatch, tmp_path):
    """A stderr that isn't valid JSON falls back to using the raw text as the
    error message, rather than crashing on the JSONDecodeError itself."""
    import mulchd.mulch as mulch_module
    from mulchd.mulch import MulchError, _run

    async def _fake_create_subprocess_exec(*args, **kwargs):
        return _FakeProc(1, stderr=b"boom: something broke")

    monkeypatch.setattr(
        mulch_module.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec
    )

    with pytest.raises(MulchError, match="boom: something broke"):
        await _run(tmp_path, ["search", "query"])


async def test_run_returns_empty_dict_for_blank_stdout(monkeypatch, tmp_path):
    import mulchd.mulch as mulch_module
    from mulchd.mulch import _run

    async def _fake_create_subprocess_exec(*args, **kwargs):
        return _FakeProc(0, stdout=b"   ")

    monkeypatch.setattr(
        mulch_module.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec
    )

    assert await _run(tmp_path, ["init"]) == {}


async def test_run_parses_json_stdout_on_success(monkeypatch, tmp_path):
    import mulchd.mulch as mulch_module
    from mulchd.mulch import _run

    async def _fake_create_subprocess_exec(*args, **kwargs):
        return _FakeProc(0, stdout=b'{"success": true, "count": 3}')

    monkeypatch.setattr(
        mulch_module.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec
    )

    assert await _run(tmp_path, ["status"]) == {"success": True, "count": 3}


async def test_search_domains_runs_per_domain_calls_concurrently(monkeypatch, tmp_path):
    """Specific-domain search must not spawn its ml subprocesses one at a time —
    verified by having each fake call block until all have started."""
    import asyncio

    from mulchd.mulch import search_domains

    domains = ["a", "b", "c"]
    started = asyncio.Event()
    start_count = 0

    async def _fake_run(mulch_dir, args, stdin_data=None):
        nonlocal start_count
        start_count += 1
        if start_count == len(domains):
            started.set()
        await asyncio.wait_for(started.wait(), timeout=1)
        domain = args[args.index("--domain") + 1]
        return {"domains": [{"domain": domain, "matches": [{"id": f"m-{domain}"}]}]}

    import mulchd.mulch as mulch_module

    monkeypatch.setattr(mulch_module, "_run", _fake_run)

    results = await search_domains(tmp_path, "query", domains=domains)
    assert [r["_domain"] for r in results] == domains


# ---------------------------------------------------------------------------
# _extract_matches — pure function
# ---------------------------------------------------------------------------


def test_extract_matches_non_dict_input_returns_empty():
    from mulchd.mulch import _extract_matches

    assert _extract_matches([1, 2, 3]) == []


def test_extract_matches_empty_domains_list():
    from mulchd.mulch import _extract_matches

    assert _extract_matches({"domains": []}) == []


def test_extract_matches_tags_each_record_with_its_domain():
    from mulchd.mulch import _extract_matches

    result = {
        "domains": [
            {"domain": "infra", "matches": [{"id": "mx-1"}, {"id": "mx-2"}]},
            {"domain": "ops", "matches": [{"id": "mx-3"}]},
        ]
    }
    matches = _extract_matches(result)
    assert [m["id"] for m in matches] == ["mx-1", "mx-2", "mx-3"]
    assert matches[0]["_domain"] == "infra"
    assert matches[1]["_domain"] == "infra"
    assert matches[2]["_domain"] == "ops"


# ---------------------------------------------------------------------------
# _find_written_record — pure function
# ---------------------------------------------------------------------------


def test_find_written_record_missing_file_returns_none(tmp_path):
    from mulchd.mulch import _find_written_record

    result = _find_written_record(
        tmp_path / "nope.jsonl", {"recorded_at": "t", "owner": "carlos", "type": "convention"}
    )
    assert result is None


def test_find_written_record_skips_malformed_lines_and_finds_newest_match(tmp_path):
    """The search scans newest-first (reversed) — put the malformed/blank
    lines AFTER the target match in the file so reversed iteration has to
    walk past them (skipping each) before reaching the real match, exactly
    like it would with genuinely interleaved bad data."""
    from mulchd.mulch import _find_written_record

    jsonl = tmp_path / "domain.jsonl"
    jsonl.write_text(
        '{"id": "mx-target", "recorded_at": "t1", "owner": "carlos", "type": "convention"}\n'
        "\n"
        "not json at all\n"
    )
    result = _find_written_record(
        jsonl, {"recorded_at": "t1", "owner": "carlos", "type": "convention"}
    )
    assert result is not None
    assert result["id"] == "mx-target"


def test_find_written_record_returns_none_when_no_match():
    from mulchd.mulch import _find_written_record

    result = _find_written_record(
        Path("/dev/null"), {"recorded_at": "x", "owner": "carlos", "type": "convention"}
    )
    assert result is None


# ---------------------------------------------------------------------------
# Real-ml wrapper smoke tests — edit/delete/restore/outcome/search, only ever
# exercised through monkeypatched fakes in the tier2 handler tests until now.
# ---------------------------------------------------------------------------


@ml_available
async def test_live_edit_record_updates_content(data_path, tmp_path):
    from mulchd.domains import mulch_dir
    from mulchd.mulch import edit_record, init_ml_project, write_record

    m_dir = mulch_dir("acme", "wraptest")
    await init_ml_project(m_dir)
    written = await write_record(
        m_dir,
        "infra",
        {"type": "convention", "classification": "tactical", "content": "v1", "owner": "carlos"},
    )
    result = await edit_record(m_dir, "infra", written["id"], {"content": "v2"})
    assert result["record"]["content"] == "v2"
    on_disk = (m_dir / "expertise" / "infra.jsonl").read_text()
    assert '"content":"v2"' in on_disk.replace(" ", "") or "v2" in on_disk


@ml_available
async def test_live_edit_record_joins_list_valued_field(data_path):
    """List-valued updates (relates_to, supersedes, files) get comma-joined
    before being passed as a single CLI flag value."""
    from mulchd.domains import mulch_dir
    from mulchd.mulch import edit_record, init_ml_project, write_record

    m_dir = mulch_dir("acme", "wraptest-listfield")
    await init_ml_project(m_dir)
    target = await write_record(
        m_dir,
        "infra",
        {
            "type": "convention",
            "classification": "tactical",
            "content": "target",
            "owner": "carlos",
        },
    )
    other = await write_record(
        m_dir,
        "infra",
        {"type": "convention", "classification": "tactical", "content": "other", "owner": "carlos"},
    )
    result = await edit_record(m_dir, "infra", target["id"], {"relates_to": [other["id"]]})
    assert other["id"] in result["record"].get("relates_to", [])


async def test_write_record_raises_when_fallback_lookup_also_fails(monkeypatch, tmp_path):
    """If ml reports the write succeeded but returns no record object, and
    the JSONL fallback lookup can't find a match either, write_record must
    raise rather than silently return something bogus."""
    import mulchd.mulch as mulch_module
    from mulchd.mulch import MulchError, write_record

    async def _fake_run(mulch_dir, args, stdin_data=None):
        return {"success": True, "created": 1}

    monkeypatch.setattr(mulch_module, "_run", _fake_run)
    monkeypatch.setattr(mulch_module, "_find_written_record", lambda path, record: None)

    with pytest.raises(MulchError, match="ml record returned no record object"):
        await write_record(tmp_path, "infra", {"type": "convention", "content": "x"})


async def test_write_record_raises_record_not_written_error_on_skip(monkeypatch, tmp_path):
    """ml skips a duplicate for anonymous types (convention/failure) —
    created=0, updated=0. write_record must raise RecordNotWrittenError,
    not MulchError, carrying ml's summary so the caller can react gracefully
    instead of treating this as a call failure."""
    import mulchd.mulch as mulch_module
    from mulchd.mulch import RecordNotWrittenError, write_record

    summary = {
        "success": True,
        "command": "record",
        "action": "stdin",
        "domain": "infra",
        "created": 0,
        "updated": 0,
        "skipped": 1,
        "errors": [],
        "warnings": [],
    }

    async def _fake_run(mulch_dir, args, stdin_data=None):
        return summary

    monkeypatch.setattr(mulch_module, "_run", _fake_run)

    with pytest.raises(RecordNotWrittenError) as exc_info:
        await write_record(tmp_path, "infra", {"type": "convention", "content": "x"})
    assert exc_info.value.summary == summary


async def test_write_record_raises_record_not_written_error_on_update(monkeypatch, tmp_path):
    """ml upserts a duplicate for named types (decision/pattern/reference/
    guide) — created=0, updated=1. Same RecordNotWrittenError as the skip
    case, since mulchd never wants either to be reported as a successful
    new write."""
    import mulchd.mulch as mulch_module
    from mulchd.mulch import RecordNotWrittenError, write_record

    summary = {
        "success": True,
        "command": "record",
        "action": "stdin",
        "domain": "infra",
        "created": 0,
        "updated": 1,
        "skipped": 0,
        "errors": [],
        "warnings": [],
    }

    async def _fake_run(mulch_dir, args, stdin_data=None):
        return summary

    monkeypatch.setattr(mulch_module, "_run", _fake_run)

    with pytest.raises(RecordNotWrittenError) as exc_info:
        await write_record(tmp_path, "infra", {"type": "decision", "title": "x", "rationale": "y"})
    assert exc_info.value.summary == summary


@ml_available
async def test_live_delete_record_archives_it(data_path):
    from mulchd.domains import mulch_dir
    from mulchd.mulch import delete_record, init_ml_project, write_record

    m_dir = mulch_dir("acme", "wraptest2")
    await init_ml_project(m_dir)
    written = await write_record(
        m_dir,
        "infra",
        {"type": "convention", "classification": "tactical", "content": "v1", "owner": "carlos"},
    )
    await delete_record(m_dir, "infra", written["id"])
    live = m_dir / "expertise" / "infra.jsonl"
    assert not live.exists() or written["id"] not in live.read_text()
    archive = m_dir / "archive" / "infra.jsonl"
    assert archive.exists()
    assert written["id"] in archive.read_text()


@ml_available
async def test_live_restore_record_moves_it_back_to_expertise(data_path):
    from mulchd.domains import mulch_dir
    from mulchd.mulch import (
        delete_record,
        init_ml_project,
        restore_record,
        write_record,
    )

    m_dir = mulch_dir("acme", "wraptest3")
    await init_ml_project(m_dir)
    written = await write_record(
        m_dir,
        "infra",
        {"type": "convention", "classification": "tactical", "content": "v1", "owner": "carlos"},
    )
    await delete_record(m_dir, "infra", written["id"])
    result = await restore_record(m_dir, written["id"])
    assert result["id"] == written["id"]
    live = m_dir / "expertise" / "infra.jsonl"
    assert written["id"] in live.read_text()


@ml_available
async def test_live_record_outcome_appends_to_record(data_path):
    from mulchd.domains import mulch_dir
    from mulchd.mulch import (
        OutcomeStatus,
        init_ml_project,
        record_outcome,
        write_record,
    )

    m_dir = mulch_dir("acme", "wraptest4")
    await init_ml_project(m_dir)
    written = await write_record(
        m_dir,
        "infra",
        {"type": "convention", "classification": "tactical", "content": "v1", "owner": "carlos"},
    )
    await record_outcome(m_dir, "infra", written["id"], OutcomeStatus.SUCCESS, notes="worked")
    on_disk = (m_dir / "expertise" / "infra.jsonl").read_text()
    assert '"status":"success"' in on_disk.replace(" ", "") or "success" in on_disk


async def test_record_outcome_passes_agent_flag_when_given(monkeypatch, tmp_path):
    import mulchd.mulch as mulch_module
    from mulchd.mulch import OutcomeStatus, record_outcome

    captured_args = []

    async def _fake_run(mulch_dir, args, stdin_data=None):
        captured_args.append(args)
        return {"success": True}

    monkeypatch.setattr(mulch_module, "_run", _fake_run)

    await record_outcome(tmp_path, "infra", "mx-1", OutcomeStatus.SUCCESS, agent="carlos")

    assert "--agent" in captured_args[0]
    assert captured_args[0][captured_args[0].index("--agent") + 1] == "carlos"


async def test_record_outcome_omits_agent_flag_when_not_given(monkeypatch, tmp_path):
    import mulchd.mulch as mulch_module
    from mulchd.mulch import OutcomeStatus, record_outcome

    captured_args = []

    async def _fake_run(mulch_dir, args, stdin_data=None):
        captured_args.append(args)
        return {"success": True}

    monkeypatch.setattr(mulch_module, "_run", _fake_run)

    await record_outcome(tmp_path, "infra", "mx-1", OutcomeStatus.SUCCESS)

    assert "--agent" not in captured_args[0]


@ml_available
async def test_live_search_domains_finds_seeded_record(data_path):
    from mulchd.domains import mulch_dir
    from mulchd.mulch import init_ml_project, search_domains, write_record

    m_dir = mulch_dir("acme", "wraptest5")
    await init_ml_project(m_dir)
    await write_record(
        m_dir,
        "infra",
        {
            "type": "convention",
            "classification": "tactical",
            "content": "Always enable S3 bucket versioning",
            "owner": "carlos",
        },
    )
    results = await search_domains(m_dir, "S3 bucket versioning")
    assert len(results) >= 1
    assert results[0]["_domain"] == "infra"


@ml_available
async def test_live_search_domains_scoped_to_specific_domains(data_path):
    from mulchd.domains import mulch_dir
    from mulchd.mulch import init_ml_project, search_domains, write_record

    m_dir = mulch_dir("acme", "wraptest6")
    await init_ml_project(m_dir)
    await write_record(
        m_dir,
        "infra",
        {
            "type": "convention",
            "classification": "tactical",
            "content": "deploy rule",
            "owner": "carlos",
        },
    )
    await write_record(
        m_dir,
        "ops",
        {
            "type": "convention",
            "classification": "tactical",
            "content": "deploy rule",
            "owner": "carlos",
        },
    )
    results = await search_domains(m_dir, "deploy rule", domains=["infra"])
    assert all(r["_domain"] == "infra" for r in results)
