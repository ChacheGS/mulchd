import pytest


async def test_project_overview_page_renders(admin_client):
    from mulchd.models import Organization, Project

    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    resp = await admin_client.get(f"/admin/p/{org.slug}/{project.slug}/")
    assert resp.status_code == 200
    assert project.display_name in resp.text


async def test_project_overview_page_404s_for_unknown_slug(admin_client):
    resp = await admin_client.get("/admin/p/nope/nope/")
    assert resp.status_code == 404


async def test_project_detail_renders_invite_rows(admin_client):
    from datetime import UTC, datetime, timedelta

    from mulchd.models import (
        InviteLink,
        InviteUse,
        Organization,
        Project,
        Role,
        User,
    )

    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    user = await User.create(username="bob", display_name="Bob", token_hash="x")
    active = await InviteLink.create(
        token="t1", project=project, role=Role.ADMIN, max_uses=3, use_count=1
    )
    await InviteLink.create(
        token="t2",
        project=project,
        role=Role.READER,
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    await InviteLink.create(token="t3", project=project, role=Role.WRITER, max_uses=2, use_count=2)
    await InviteLink.create(token="t4", project=project, role=Role.READER, revoked=True)
    await InviteUse.create(invite=active, user=user)

    resp = await admin_client.get(f"/admin/p/{org.slug}/{project.slug}/")
    assert resp.status_code == 200
    assert "badge-admin" in resp.text
    assert "badge-writer" in resp.text
    assert "expired" in resp.text
    assert "exhausted" in resp.text
    assert "revoked" in resp.text
    assert "bob" in resp.text


async def test_project_detail_shows_invite_creator(admin_client):
    from mulchd.models import Organization, Project

    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    await admin_client.post(
        f"/admin/projects/{project.id}/invites",
        data={"role": "writer", "max_uses": "", "expires_in": "", "allowed_email_domains": ""},
    )

    resp = await admin_client.get(f"/admin/p/{org.slug}/{project.slug}/")
    assert resp.status_code == 200
    assert "by admin" in resp.text


async def test_project_overview_links_to_filtered_memberships_and_tokens(admin_client):
    from mulchd.models import Organization, Project

    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)

    resp = await admin_client.get(f"/admin/p/{org.slug}/{project.slug}/")
    assert resp.status_code == 200
    assert "/admin/memberships?project=acme/infra" in resp.text
    assert "/admin/project-tokens?project=acme/infra" in resp.text
    assert "/admin/activity?project=acme/infra" in resp.text


async def test_project_overview_shows_usage_panel(admin_client):
    from mulchd.models import Organization, Project

    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)

    resp = await admin_client.get(f"/admin/p/{org.slug}/{project.slug}/")
    assert resp.status_code == 200
    assert 'id="usage-btn-day"' in resp.text
    assert 'id="usage-btn-week"' in resp.text
    assert 'id="usage-btn-month"' in resp.text
    assert 'id="usage-chart"' in resp.text
    assert 'id="usage-by-tool"' in resp.text
    assert 'id="usage-by-user"' in resp.text
    assert "/admin/api/usage/acme/infra" in resp.text


async def test_project_overview_shows_language_edit_form(admin_client):
    from mulchd.models import Organization, Project

    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)

    resp = await admin_client.get(f"/admin/p/{org.slug}/{project.slug}/")
    assert resp.status_code == 200
    assert f'action="/admin/projects/{project.id}/language"' in resp.text


async def test_set_project_language_404s_for_unknown_project(admin_client):
    resp = await admin_client.post(
        "/admin/projects/999999/language",
        data={"knowledge_language": "en"},
        follow_redirects=False,
    )
    assert resp.status_code == 404


async def test_set_project_language_redirects_to_project_detail(admin_client):
    from mulchd.models import Organization, Project

    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)

    resp = await admin_client.post(
        f"/admin/projects/{project.id}/language",
        data={"knowledge_language": "en"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/admin/p/{org.slug}/{project.slug}/"

    await project.refresh_from_db()
    assert project.knowledge_language == "en"
