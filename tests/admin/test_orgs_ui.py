import pytest


async def test_create_org(admin_client):
    resp = await admin_client.post(
        "/admin/orgs", data={"slug": "acme", "display_name": "Acme Corp"}, follow_redirects=False
    )
    assert resp.status_code == 303


async def test_create_org_rejects_slash_in_slug(admin_client):
    """A slug containing '/' would break the org/project-slug join used
    throughout the admin UI (cookies, ?project= params, /admin/p/... routes)."""
    from mulchd.models import Organization

    resp = await admin_client.post(
        "/admin/orgs", data={"slug": "ac/me", "display_name": "Acme Corp"}, follow_redirects=False
    )
    assert resp.status_code == 422
    assert "lowercase letters, numbers, and hyphens" in resp.text
    assert await Organization.filter(slug="ac/me").first() is None


async def test_create_org_logs_event(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory

    resp = await admin_client.post(
        "/admin/orgs",
        data={"slug": "logorg", "display_name": "Log Org"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    event = await InstanceEvent.get(category=InstanceEventCategory.ORG_CREATED)
    assert event.detail == {"org_slug": "logorg"}


async def test_create_org_duplicate_does_not_log(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory

    await admin_client.post("/admin/orgs", data={"slug": "duporg", "display_name": "Dup Org"})
    resp = await admin_client.post(
        "/admin/orgs",
        data={"slug": "duporg", "display_name": "Dup Org 2"},
        follow_redirects=False,
    )
    assert resp.status_code == 409

    count = await InstanceEvent.filter(category=InstanceEventCategory.ORG_CREATED).count()
    assert count == 1


async def test_org_detail_page_renders(admin_client):
    from mulchd.models import Organization, Project

    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)

    resp = await admin_client.get(f"/admin/orgs/{org.slug}")
    assert resp.status_code == 200
    assert "Acme Corp" in resp.text
    assert project.slug in resp.text
    assert f'href="/admin/p/{org.slug}/{project.slug}/"' in resp.text


async def test_org_detail_page_404s_for_unknown_slug(admin_client):
    resp = await admin_client.get("/admin/orgs/nope")
    assert resp.status_code == 404


async def test_create_project_under_org(admin_client):
    from mulchd.models import Organization

    org = await Organization.create(slug="acme", display_name="Acme Corp")
    resp = await admin_client.post(
        f"/admin/orgs/{org.slug}/projects",
        data={"slug": "data-platform", "display_name": "Data Platform"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/admin/orgs/{org.slug}"


async def test_create_project_under_org_rejects_slash_in_slug(admin_client):
    from mulchd.models import Organization, Project

    org = await Organization.create(slug="acme", display_name="Acme Corp")
    resp = await admin_client.post(
        f"/admin/orgs/{org.slug}/projects",
        data={"slug": "data/platform", "display_name": "Data Platform"},
        follow_redirects=False,
    )
    assert resp.status_code == 422
    assert "lowercase letters, numbers, and hyphens" in resp.text
    assert await Project.filter(slug="data/platform").first() is None


async def test_create_project_under_org_logs_event(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory, Organization

    org = await Organization.create(slug="logprojorg", display_name="Log Proj Org")
    resp = await admin_client.post(
        f"/admin/orgs/{org.slug}/projects",
        data={"slug": "logproj", "display_name": "Log Proj"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    event = await InstanceEvent.get(category=InstanceEventCategory.PROJECT_CREATED)
    assert event.project_id is not None


async def test_create_project_under_org_duplicate_does_not_log(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory, Organization

    org = await Organization.create(slug="dupprojorg", display_name="Dup Proj Org")
    await admin_client.post(
        f"/admin/orgs/{org.slug}/projects",
        data={"slug": "dupproj", "display_name": "Dup Proj"},
    )
    resp = await admin_client.post(
        f"/admin/orgs/{org.slug}/projects",
        data={"slug": "dupproj", "display_name": "Dup Proj 2"},
        follow_redirects=False,
    )
    assert resp.status_code == 409

    count = await InstanceEvent.filter(category=InstanceEventCategory.PROJECT_CREATED).count()
    assert count == 1


async def test_create_project_under_unknown_org_404s(admin_client):
    resp = await admin_client.post(
        "/admin/orgs/nope/projects",
        data={"slug": "x", "display_name": "X"},
        follow_redirects=False,
    )
    assert resp.status_code == 404


async def test_orgs_page_pick_for_shows_banner_and_org_links_carry_it(admin_client):
    from mulchd.models import Organization

    org = await Organization.create(slug="acme", display_name="Acme Corp")

    resp = await admin_client.get("/admin/orgs?pick_for=records")
    assert resp.status_code == 200
    assert "Pick a project to view its" in resp.text
    assert f'href="/admin/orgs/{org.slug}?pick_for=records"' in resp.text


async def test_orgs_page_unknown_pick_for_is_ignored(admin_client):
    from mulchd.models import Organization

    org = await Organization.create(slug="acme", display_name="Acme Corp")

    resp = await admin_client.get("/admin/orgs?pick_for=bogus")
    assert resp.status_code == 200
    assert "Pick a project" not in resp.text
    assert f'href="/admin/orgs/{org.slug}"' in resp.text


async def test_org_detail_pick_for_shows_tab_links(admin_client):
    from mulchd.models import Organization, Project

    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)

    resp = await admin_client.get(f"/admin/orgs/{org.slug}?pick_for=records")
    assert resp.status_code == 200
    assert "Records" in resp.text
    assert f'href="/admin/p/{org.slug}/{project.slug}/records"' in resp.text


async def test_org_detail_unknown_pick_for_is_ignored(admin_client):
    from mulchd.models import Organization, Project

    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)

    resp = await admin_client.get(f"/admin/orgs/{org.slug}?pick_for=bogus")
    assert resp.status_code == 200
    assert "Pick a project" not in resp.text
    assert f'href="/admin/p/{org.slug}/{project.slug}/"' in resp.text
