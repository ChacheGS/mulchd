import pytest


async def test_sidebar_groups_render(admin_client):
    resp = await admin_client.get("/admin/users")
    assert resp.status_code == 200
    assert "Overview" in resp.text
    assert "Instance" in resp.text
    assert "Knowledge" in resp.text


async def test_sidebar_knowledge_links_fallback_to_projects_list_with_no_context(admin_client):
    """With no last-visited-project cookie and no project in the current page's
    context, the Knowledge links point at the Projects list with a `pick_for`
    hint (which shows an explicit picker banner) rather than a broken or
    guessed URL."""
    resp = await admin_client.get("/admin/users")
    assert resp.status_code == 200
    assert 'href="/admin/projects?pick_for=records"' in resp.text
    assert 'href="/admin/projects?pick_for=record-activity"' in resp.text
    assert 'href="/admin/projects?pick_for=quality"' in resp.text
    # The Instance-group "Projects" nav item itself stays a plain link.
    assert resp.text.count('href="/admin/projects"') == 1
    assert "/admin/p/" not in resp.text


async def test_sidebar_knowledge_links_use_last_project_cookie(admin_client):
    admin_client.cookies.set("admin_last_project", "acme/infra")
    resp = await admin_client.get("/admin/users")
    assert resp.status_code == 200
    assert 'href="/admin/p/acme/infra/records"' in resp.text
    assert 'href="/admin/p/acme/infra/record-activity"' in resp.text
    assert 'href="/admin/p/acme/infra/quality"' in resp.text
