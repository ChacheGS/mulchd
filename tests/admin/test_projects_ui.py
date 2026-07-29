import pytest


async def test_create_project(admin_client):
    await admin_client.post("/admin/orgs", data={"slug": "acme", "display_name": "Acme"})
    resp = await admin_client.get("/admin/orgs")
    from mulchd.models import Organization

    org = await Organization.get(slug="acme")
    resp = await admin_client.post(
        "/admin/projects",
        data={"org_id": org.id, "slug": "data-platform", "display_name": "Data Platform"},
        follow_redirects=False,
    )
    assert resp.status_code == 303


async def test_project_detail_page_renders(admin_client):
    from mulchd.models import Organization, Project
    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    resp = await admin_client.get(f"/admin/projects/{project.id}")
    assert resp.status_code == 200
    assert project.display_name in resp.text


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
    active = await InviteLink.create(token="t1", project=project, role=Role.ADMIN, max_uses=3, use_count=1)
    await InviteLink.create(
        token="t2", project=project, role=Role.READER,
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    await InviteLink.create(token="t3", project=project, role=Role.WRITER, max_uses=2, use_count=2)
    await InviteLink.create(token="t4", project=project, role=Role.READER, revoked=True)
    await InviteUse.create(invite=active, user=user)

    resp = await admin_client.get(f"/admin/projects/{project.id}")
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

    resp = await admin_client.get(f"/admin/projects/{project.id}")
    assert resp.status_code == 200
    assert "by admin" in resp.text


async def test_create_project_logs_event(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory, Organization

    org = await Organization.create(slug="logprojorg", display_name="Log Proj Org")
    resp = await admin_client.post(
        "/admin/projects",
        data={"org_id": org.id, "slug": "logproj", "display_name": "Log Proj"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    event = await InstanceEvent.get(category=InstanceEventCategory.PROJECT_CREATED)
    assert event.project_id is not None


async def test_create_project_duplicate_does_not_log(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory, Organization

    org = await Organization.create(slug="dupprojorg", display_name="Dup Proj Org")
    await admin_client.post(
        "/admin/projects",
        data={"org_id": org.id, "slug": "dupproj", "display_name": "Dup Proj"},
    )
    resp = await admin_client.post(
        "/admin/projects",
        data={"org_id": org.id, "slug": "dupproj", "display_name": "Dup Proj 2"},
        follow_redirects=False,
    )
    assert resp.status_code == 409

    count = await InstanceEvent.filter(category=InstanceEventCategory.PROJECT_CREATED).count()
    assert count == 1
