import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

from mulchd.models import Organization, Project
from tests.connect.conftest import _authed_client

# ── projects ────────────────────────────────────────────────────────────────


async def test_connect_projects_requires_auth(client):
    resp = await client.get("/connect/projects", follow_redirects=False)
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


async def test_connect_projects_lists_memberships(client, alice_and_project):
    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    resp = await client.get("/connect/projects")
    assert resp.status_code == 200
    assert "demo" in resp.text


async def test_connect_projects_shows_invalid_invite_error(client, alice_and_project):
    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    resp = await client.get("/connect/projects", params={"invite_error": "invalid"})
    assert resp.status_code == 200
    assert "invite link" in resp.text.lower()
    assert "no longer valid" in resp.text.lower()


async def test_connect_projects_shows_domain_denied_invite_error(client, alice_and_project):
    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    resp = await client.get("/connect/projects", params={"invite_error": "domain_denied"})
    assert resp.status_code == 200
    assert "email" in resp.text.lower()
    assert "authorized" in resp.text.lower()


async def test_connect_projects_ignores_unrecognized_invite_error(client, alice_and_project):
    """An unrecognized/tampered invite_error value must not be reflected back
    into the page verbatim — only known outcomes get a message."""
    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    resp = await client.get("/connect/projects", params={"invite_error": "<script>evil</script>"})
    assert resp.status_code == 200
    assert "<script>evil</script>" not in resp.text


async def test_connect_projects_no_invite_error_banner_without_param(client, alice_and_project):
    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    resp = await client.get("/connect/projects")
    assert resp.status_code == 200
    assert 'class="alert alert-warning"' not in resp.text


async def test_connect_projects_shows_admin_link_for_superadmin(admin_client):
    resp = await admin_client.get("/connect/projects")
    assert resp.status_code == 200
    assert 'href="/admin/"' in resp.text


async def test_connect_projects_hides_admin_link_for_non_admin(client, alice_and_project):
    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    resp = await client.get("/connect/projects")
    assert resp.status_code == 200
    assert 'href="/admin/"' not in resp.text


# ── project page ────────────────────────────────────────────────────────────


async def test_connect_project_page_renders(client, alice_and_project):
    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    resp = await client.get("/connect/projects/acme/demo")
    assert resp.status_code == 200
    assert "project-page" in resp.text


async def test_connect_project_page_nonmember_404(client, alice_and_project):
    user, token, *_ = alice_and_project
    # Create a second org/project that alice is not a member of
    org2 = await Organization.create(slug="other", display_name="Other")
    await Project.create(slug="secret", display_name="Secret", org=org2)
    await _authed_client(client, token)
    resp = await client.get("/connect/projects/other/secret")
    assert resp.status_code == 404
