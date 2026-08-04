import pytest


async def test_sidebar_groups_render(admin_client):
    resp = await admin_client.get("/admin/users")
    assert resp.status_code == 200
    assert "Overview" in resp.text
    assert "Instance" in resp.text
    assert "Project" in resp.text


async def test_sidebar_project_tab_links_fallback_to_projects_list_with_no_context(admin_client):
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
    # No tab link points at a guessed project URL (the sidebar's project
    # switcher <select> legitimately references "/admin/p/" in its onchange
    # JS regardless of context — only hrefs are asserted here).
    assert 'href="/admin/p/' not in resp.text


async def test_sidebar_project_tab_links_use_last_project_cookie(admin_client):
    admin_client.cookies.set("admin_last_project", "acme/infra")
    resp = await admin_client.get("/admin/users")
    assert resp.status_code == 200
    assert 'href="/admin/p/acme/infra/records"' in resp.text
    assert 'href="/admin/p/acme/infra/record-activity"' in resp.text
    assert 'href="/admin/p/acme/infra/quality"' in resp.text


async def test_sidebar_project_switcher_renders_options(admin_client):
    from mulchd.models import Organization, Project

    org = await Organization.create(slug="acme", display_name="Acme")
    await Project.create(slug="infra", display_name="Infra", org=org)
    await Project.create(slug="web", display_name="Web", org=org)

    resp = await admin_client.get("/admin/users")
    assert resp.status_code == 200
    assert '<option value="acme/infra"' in resp.text
    assert '<option value="acme/web"' in resp.text


async def test_sidebar_project_switcher_preselects_cookie_project(admin_client):
    from mulchd.models import Organization, Project

    org = await Organization.create(slug="acme", display_name="Acme")
    await Project.create(slug="infra", display_name="Infra", org=org)

    admin_client.cookies.set("admin_last_project", "acme/infra")
    resp = await admin_client.get("/admin/users")
    assert resp.status_code == 200
    assert '<option value="acme/infra" selected>' in resp.text


async def test_sidebar_project_switcher_targets_overview_from_non_project_page(admin_client):
    resp = await admin_client.get("/admin/users")
    assert resp.status_code == 200
    assert (
        "location.href = '/admin/p/' + this.value.split('/').map(encodeURIComponent).join('/') + '/'"
        in resp.text
    )


async def test_sidebar_project_switcher_preserves_tab_on_project_page(admin_client, tmp_path, monkeypatch):
    from mulchd.config import settings
    from mulchd.models import Organization, Project

    monkeypatch.setattr(settings, "data_path", tmp_path)
    org = await Organization.create(slug="acme", display_name="Acme")
    await Project.create(slug="infra", display_name="Infra", org=org)

    resp = await admin_client.get("/admin/p/acme/infra/records")
    assert resp.status_code == 200
    assert (
        "location.href = '/admin/p/' + this.value.split('/').map(encodeURIComponent).join('/') + '/records'"
        in resp.text
    )


async def test_project_home_header_has_no_switcher(admin_client, tmp_path, monkeypatch):
    """The header's own switcher is removed — switching now happens from the
    sidebar only. Breadcrumb text and tabs stay."""
    from mulchd.config import settings
    from mulchd.models import Organization, Project

    monkeypatch.setattr(settings, "data_path", tmp_path)
    org = await Organization.create(slug="acme", display_name="Acme")
    await Project.create(slug="infra", display_name="Infra", org=org)

    resp = await admin_client.get("/admin/p/acme/infra/records")
    assert resp.status_code == 200
    assert 'class="project-switcher"' not in resp.text
    assert 'class="project-breadcrumb-org"' in resp.text
