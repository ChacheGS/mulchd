"""
Tests for /admin/quality — corpus-quality report rendering.

Strategy: real ml audit integration test (gated by ml_available, same
convention as tests/test_mcp_tools.py) plus monkeypatched fixture data for
deterministic PASS/WARN/FAIL rendering-branch coverage.
"""

import shutil

import pytest

from mulchd.models import Organization, Project, Role, User, UserMembership

ml_available = pytest.mark.skipif(
    not shutil.which("ml"), reason="ml not in PATH — run via: PATH=\"$(pwd)/node_modules/.bin:$PATH\""
)


async def _setup(tmp_path, monkeypatch):
    import mulchd.domains as domains

    # test_oauth.py reloads mulchd.config, which rebinds mulchd.config.settings
    # to a new Settings instance. mulchd.domains bound `settings` by name at
    # import time and keeps the old one, so patch the object mulch_dir actually
    # reads rather than whatever `from mulchd.config import settings` returns
    # now (which may be the post-reload instance domains.py never sees).
    monkeypatch.setattr(domains.settings, "data_path", tmp_path)
    org = await Organization.create(slug="acme", display_name="Acme")
    project = await Project.create(slug="platform", display_name="Platform", org=org)
    alice = await User.create(username="alice", display_name="Alice K.", token_hash="h1")
    await UserMembership.create(user=alice, project=project, role=Role.WRITER)
    return org, project, alice


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------


async def test_quality_page_requires_auth(client):
    resp = await client.get("/admin/quality", follow_redirects=False)
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


async def test_quality_page_rejects_non_admin_user(client):
    from mulchd.auth import create_user
    from mulchd.connect import _signer

    user, _ = await create_user("regular", "Regular User")
    signed = _signer().dumps(user.id)
    client.cookies.set("mulchd_connect", signed)
    resp = await client.get("/admin/quality", follow_redirects=False)
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------


async def test_quality_page_no_project_selected_shows_empty_state(admin_client):
    resp = await admin_client.get("/admin/quality")
    assert resp.status_code == 200
    assert "select a project" in resp.text.lower()


# ---------------------------------------------------------------------------
# Real end-to-end (real ml)
# ---------------------------------------------------------------------------


@ml_available
async def test_quality_page_renders_real_audit_report(admin_client, tmp_path, monkeypatch):
    from mulchd.domains import mulch_dir
    from mulchd.mulch import init_ml_project, write_record

    org, project, alice = await _setup(tmp_path, monkeypatch)
    m_dir = mulch_dir("acme", "platform")
    await init_ml_project(m_dir)
    await write_record(
        m_dir,
        "api",
        {
            "type": "convention",
            "classification": "tactical",
            "content": "Always validate webhook signatures before processing",
            "owner": "alice",
        },
    )

    resp = await admin_client.get("/admin/quality?project=acme/platform")
    assert resp.status_code == 200
    assert "api" in resp.text
    assert "evidence" in resp.text.lower() or "coverage" in resp.text.lower()


@ml_available
async def test_quality_page_renders_when_no_conventions_recorded(admin_client, tmp_path, monkeypatch):
    """ml audit returns signals.rule_density as null (not omitted) when the
    corpus has zero convention-type records — any brand-new project or a
    domain filter that excludes conventions hits this. Must not 500."""
    from mulchd.domains import mulch_dir
    from mulchd.mulch import init_ml_project, write_record

    org, project, alice = await _setup(tmp_path, monkeypatch)
    m_dir = mulch_dir("acme", "platform")
    await init_ml_project(m_dir)
    await write_record(
        m_dir,
        "api",
        {
            "type": "decision",
            "classification": "tactical",
            "title": "Use webhook signature validation",
            "rationale": "Prevents forged webhook payloads from being processed.",
            "owner": "alice",
        },
    )

    resp = await admin_client.get("/admin/quality?project=acme/platform")
    assert resp.status_code == 200
    assert "api" in resp.text


async def test_quality_page_renders_when_a_signal_is_null(admin_client, tmp_path, monkeypatch):
    """Deterministic version of the null-signal case above, for fast/offline
    coverage without depending on real ml's actual scoring behavior."""
    import mulchd.admin.quality as quality_module

    org, project, alice = await _setup(tmp_path, monkeypatch)

    async def _fake_audit(m_dir, domain=None):
        report = _fake_report()
        report["report"]["signals"]["rule_density"] = None
        return report

    monkeypatch.setattr(quality_module, "audit_corpus", _fake_audit)

    resp = await admin_client.get("/admin/quality?project=acme/platform")
    assert resp.status_code == 200
    assert "PASS" in resp.text  # evidence_coverage still renders
    assert "FAIL" in resp.text  # floater_rate still renders


# ---------------------------------------------------------------------------
# Rendering branches (monkeypatched, deterministic)
# ---------------------------------------------------------------------------


def _fake_report(**overrides) -> dict:
    base = {
        "report": {
            "repo": "platform",
            "total_records": 4,
            "domains": ["api", "infra"],
            "type_mix": [{"type": "convention", "count": 4, "pct": 100}],
            "by_domain": [
                {
                    "domain": "api",
                    "total": 3,
                    "type_counts": {"convention": 3},
                    "high_value_pct": 33,
                    "first_recorded_at": "2026-07-01T00:00:00Z",
                    "last_recorded_at": "2026-07-20T00:00:00Z",
                },
                {
                    "domain": "infra",
                    "total": 1,
                    "type_counts": {"convention": 1},
                    "high_value_pct": 0,
                    "first_recorded_at": "2026-07-15T00:00:00Z",
                    "last_recorded_at": "2026-07-15T00:00:00Z",
                },
            ],
            "signals": {
                "evidence_coverage": {"verdict": "PASS", "value": 0.6, "threshold": 0.5, "warn_threshold": 0.3},
                "rule_density": {"verdict": "WARN", "value": 0.2, "threshold": 0.25, "warn_threshold": 0.15},
                "floater_rate": {"verdict": "FAIL", "value": 0.9, "threshold": 0.2},
            },
            "failures": ["floater_rate"],
            "warnings": ["rule_density"],
        },
        "suggestions": {
            "groups": [
                {
                    "action": "revise",
                    "headline": "1 convention lacks rule-signal language",
                    "rationale": "Conventions without rule-signal words often restate code.",
                    "record_ids": ["mx-abc123"],
                    "commands": ['ml edit mx-abc123 --content "..."'],
                }
            ]
        },
    }
    base["report"].update(overrides)
    return base


async def test_quality_page_renders_pass_warn_fail_signals(admin_client, tmp_path, monkeypatch):
    import mulchd.admin.quality as quality_module

    org, project, alice = await _setup(tmp_path, monkeypatch)

    async def _fake_audit(m_dir, domain=None):
        return _fake_report()

    monkeypatch.setattr(quality_module, "audit_corpus", _fake_audit)

    resp = await admin_client.get("/admin/quality?project=acme/platform")
    assert resp.status_code == 200
    assert "PASS" in resp.text
    assert "WARN" in resp.text
    assert "FAIL" in resp.text


async def test_quality_page_renders_per_domain_breakdown(admin_client, tmp_path, monkeypatch):
    import mulchd.admin.quality as quality_module

    org, project, alice = await _setup(tmp_path, monkeypatch)

    async def _fake_audit(m_dir, domain=None):
        return _fake_report()

    monkeypatch.setattr(quality_module, "audit_corpus", _fake_audit)

    resp = await admin_client.get("/admin/quality?project=acme/platform")
    assert "api" in resp.text
    assert "infra" in resp.text


async def test_quality_page_renders_suggestions(admin_client, tmp_path, monkeypatch):
    import mulchd.admin.quality as quality_module

    org, project, alice = await _setup(tmp_path, monkeypatch)

    async def _fake_audit(m_dir, domain=None):
        return _fake_report()

    monkeypatch.setattr(quality_module, "audit_corpus", _fake_audit)

    resp = await admin_client.get("/admin/quality?project=acme/platform")
    assert "1 convention lacks rule-signal language" in resp.text
    assert "mx-abc123" in resp.text
    assert "ml edit mx-abc123" in resp.text
    # The illustrative command is reference text only — never wrapped in
    # anything that would make it look runnable from the browser.
    suggestion_block = resp.text.split('class="suggestion-block"', 1)[1]
    assert "<form" not in suggestion_block
    assert "<button" not in suggestion_block


async def test_quality_page_forwards_domain_filter_to_audit_corpus(admin_client, tmp_path, monkeypatch):
    """The domain= query param must reach audit_corpus, and the Clear link
    must be present so the filter can be removed."""
    import mulchd.admin.quality as quality_module

    org, project, alice = await _setup(tmp_path, monkeypatch)

    received = {}

    async def _fake_audit(m_dir, domain=None):
        received["domain"] = domain
        return _fake_report()

    monkeypatch.setattr(quality_module, "audit_corpus", _fake_audit)

    resp = await admin_client.get("/admin/quality?project=acme/platform&domain=api")
    assert resp.status_code == 200
    assert received["domain"] == "api"
    assert 'value="api"' in resp.text
    assert "/admin/quality?project=acme/platform" in resp.text  # Clear link present


async def test_quality_page_omits_failures_warnings_when_empty(admin_client, tmp_path, monkeypatch):
    import mulchd.admin.quality as quality_module

    org, project, alice = await _setup(tmp_path, monkeypatch)

    async def _fake_audit(m_dir, domain=None):
        report = _fake_report()
        report["report"]["failures"] = []
        report["report"]["warnings"] = []
        return report

    monkeypatch.setattr(quality_module, "audit_corpus", _fake_audit)

    resp = await admin_client.get("/admin/quality?project=acme/platform")
    assert resp.status_code == 200
