"""Tests for GET /skill and GET /skill/{filename} endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport

from mulchd.main import app, SKILL_VERSION, _render_bundle, _extract_file, _VALID_SKILL_FILES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get(path: str, token: str | None = None) -> tuple[int, str]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(path, headers=headers)
    return resp.status_code, resp.text


# ---------------------------------------------------------------------------
# Unit-level: _render_bundle and _extract_file
# ---------------------------------------------------------------------------


def test_render_bundle_no_jinja_markers():
    """Rendered output must contain no un-rendered {{ }} markers."""
    from types import SimpleNamespace
    ctx = SimpleNamespace(org=SimpleNamespace(slug="acme"), project=SimpleNamespace(slug="infra"))
    bundle = _render_bundle("https://mulch.example.com", ctx)
    assert "{{" not in bundle
    assert "}}" not in bundle


def test_render_bundle_authenticated_substitution():
    """Authenticated render should include org/project slugs and the correct env var."""
    from types import SimpleNamespace
    ctx = SimpleNamespace(org=SimpleNamespace(slug="acme"), project=SimpleNamespace(slug="platform"))
    bundle = _render_bundle("https://mulch.example.com", ctx)
    assert "acme" in bundle
    assert "platform" in bundle
    assert "MULCHD_TOKEN_ACME_PLATFORM" in bundle
    assert "${MULCHD_TOKEN_ACME_PLATFORM}" in bundle


def test_render_bundle_anonymous_placeholders():
    """Unauthenticated render should use literal ORG/PROJECT/TOKEN_ENV_VAR placeholders."""
    bundle = _render_bundle("https://mulch.example.com", None)
    assert "ORG" in bundle
    assert "PROJECT" in bundle
    assert "TOKEN_ENV_VAR" in bundle
    assert "without a project token" in bundle


def test_render_bundle_includes_skill_version():
    bundle = _render_bundle("https://mulch.example.com", None)
    assert SKILL_VERSION in bundle


def test_render_bundle_includes_server_url():
    bundle = _render_bundle("https://mulch.example.com", None)
    assert "https://mulch.example.com" in bundle


def test_render_bundle_mcp_json_uses_http_transport():
    """The .mcp.json snippet must use the streamable HTTP transport, not sse."""
    from types import SimpleNamespace
    ctx = SimpleNamespace(org=SimpleNamespace(slug="acme"), project=SimpleNamespace(slug="infra"))
    bundle = _render_bundle("https://mulch.example.com", ctx)
    # Both the Claude Code and Desktop JSON blocks should use "http"
    assert '"type": "http"' in bundle
    assert '"type": "sse"' not in bundle


def test_extract_file_skill_md():
    bundle = _render_bundle("https://mulch.example.com", None)
    content = _extract_file(bundle, "SKILL.md")
    assert content is not None
    assert "Session Workflow" in content
    assert "<!-- mulchd:file" not in content
    assert "<!-- mulchd:endfile" not in content


def test_extract_file_setup_md():
    bundle = _render_bundle("https://mulch.example.com", None)
    content = _extract_file(bundle, "SETUP.md")
    assert content is not None
    assert "Security rules" in content
    assert "Credentials file" in content


def test_extract_file_reference_md():
    bundle = _render_bundle("https://mulch.example.com", None)
    content = _extract_file(bundle, "REFERENCE.md")
    assert content is not None
    assert "Required fields per type" in content


def test_extract_file_unknown_returns_none():
    bundle = _render_bundle("https://mulch.example.com", None)
    assert _extract_file(bundle, "NONEXISTENT.md") is None


def test_three_sections_together_cover_bundle_content():
    """SKILL + SETUP + REFERENCE concatenated should cover the main content."""
    bundle = _render_bundle("https://x.example.com", None)
    parts = [_extract_file(bundle, f) for f in ("SKILL.md", "SETUP.md", "REFERENCE.md")]
    combined = "\n\n".join(p for p in parts if p)
    assert "Session Workflow" in combined
    assert "Security rules" in combined
    assert "Required fields per type" in combined


# ---------------------------------------------------------------------------
# HTTP endpoints — anonymous
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_skill_bundle_anonymous_200():
    status, body = await _get("/skill")
    assert status == 200
    assert "mulchd skill bundle" in body
    assert "ORG" in body
    assert "without a project token" in body


@pytest.mark.anyio
async def test_skill_file_skill_md_anonymous():
    status, body = await _get("/skill/SKILL.md")
    assert status == 200
    assert "Session Workflow" in body
    assert "<!-- mulchd:file" not in body


@pytest.mark.anyio
async def test_skill_file_setup_md_anonymous():
    status, body = await _get("/skill/SETUP.md")
    assert status == 200
    assert "Security rules" in body


@pytest.mark.anyio
async def test_skill_file_reference_md_anonymous():
    status, body = await _get("/skill/REFERENCE.md")
    assert status == 200
    assert "Required fields per type" in body


@pytest.mark.anyio
async def test_skill_file_unknown_404():
    status, _ = await _get("/skill/nonsense.md")
    assert status == 404


@pytest.mark.anyio
async def test_skill_file_traversal_rejected():
    status, _ = await _get("/skill/../main.py")
    assert status == 404


# ---------------------------------------------------------------------------
# HTTP endpoints — authenticated
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_skill_bundle_authenticated(db):
    import hashlib
    from mulchd.models import Organization, Project, User, UserMembership, Role, ProjectToken

    org = await Organization.create(slug="widget-co", display_name="Widget Co")
    proj = await Project.create(slug="backend", display_name="Backend", org=org)
    user = await User.create(username="alice", display_name="Alice", token_hash="placeholder")

    raw_token = "prj_testtoken_abc"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    await UserMembership.create(user=user, project=proj, role=Role.WRITER)
    await ProjectToken.create(token_hash=token_hash, label="test", user=user, project=proj)

    status, body = await _get("/skill", token=raw_token)
    assert status == 200
    assert "widget-co" in body
    assert "backend" in body
    assert "MULCHD_TOKEN_WIDGET_CO_BACKEND" in body
    assert "without a project token" not in body  # personalized, not anonymous


@pytest.mark.anyio
async def test_skill_bundle_bad_token_falls_back_to_anonymous():
    """An invalid token should not cause a 401 — fall back to anonymous render."""
    status, body = await _get("/skill", token="prj_invalid_garbage")
    assert status == 200
    assert "ORG" in body
    assert "without a project token" in body
