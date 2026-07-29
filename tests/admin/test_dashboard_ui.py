import pytest


async def test_dashboard_requires_auth(client):
    resp = await client.get("/admin/", follow_redirects=False)
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


async def test_dashboard_rejects_non_admin_user(client):
    from mulchd.auth import create_user
    from mulchd.connect import _signer

    user, _ = await create_user("regular", "Regular User")
    signed = _signer().dumps(user.id)
    client.cookies.set("mulchd_connect", signed)
    resp = await client.get("/admin/", follow_redirects=False)
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


async def test_dashboard_renders(admin_client):
    resp = await admin_client.get("/admin/")
    assert resp.status_code == 200
    assert "Dashboard" in resp.text


async def test_dashboard_renders_project_stats(admin_client):
    """With projects and tool calls present, the per-project aggregation
    loops (never exercised by the empty-state test above) must run."""
    from mulchd.models import Organization, Project, ToolCall, User

    org = await Organization.create(slug="acme", display_name="Acme")
    project = await Project.create(slug="demo", display_name="Demo Project", org=org)
    user = await User.create(username="dashuser", display_name="Dash User", token_hash="h-dash")
    await ToolCall.create(project=project, author=user, tool="read_records", client="test")
    await ToolCall.create(project=project, author=user, tool="read_records", client="test")
    await ToolCall.create(project=project, author=user, tool="write_decision", client="test")

    resp = await admin_client.get("/admin/")
    assert resp.status_code == 200
    assert "Demo Project" in resp.text
    assert "read_records" in resp.text
    assert "write_decision" in resp.text
