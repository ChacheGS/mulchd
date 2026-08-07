"""Pagination on the cross-project admin list pages (Orgs, Users, Memberships,
Project tokens), and the shared paginate() helper they're built on."""

import pytest


async def test_paginate_slices_and_counts_pages(db):
    from mulchd.admin._shared import paginate
    from mulchd.models import Organization

    for i in range(5):
        await Organization.create(slug=f"org{i}", display_name=f"Org {i}")

    qs = Organization.all().order_by("slug")
    page1, total_pages = await paginate(qs, page=1, page_size=2)
    assert [o.slug for o in page1] == ["org0", "org1"]
    assert total_pages == 3

    page3, total_pages = await paginate(Organization.all().order_by("slug"), page=3, page_size=2)
    assert [o.slug for o in page3] == ["org4"]
    assert total_pages == 3


async def test_paginate_clamps_below_page_one(db):
    from mulchd.admin._shared import paginate
    from mulchd.models import Organization

    await Organization.create(slug="acme", display_name="Acme")

    items, total_pages = await paginate(Organization.all(), page=0, page_size=10)
    assert len(items) == 1
    assert total_pages == 1


async def test_paginate_on_empty_queryset_reports_one_page(db):
    from mulchd.admin._shared import paginate
    from mulchd.models import Organization

    items, total_pages = await paginate(Organization.all(), page=1, page_size=10)
    assert items == []
    assert total_pages == 1


async def test_orgs_page_paginates(admin_client, monkeypatch):
    from mulchd.models import Organization

    monkeypatch.setenv("MULCHD_POLICY_DEFAULT_PAGE_SIZE", "2")
    for i in range(3):
        await Organization.create(slug=f"org{i}", display_name=f"Org {i}")

    resp = await admin_client.get("/admin/orgs")
    assert resp.status_code == 200
    assert "org0" in resp.text
    assert "org1" in resp.text
    assert "org2" not in resp.text
    assert "Page 1 of 2" in resp.text
    assert 'href="?page=2"' in resp.text

    resp2 = await admin_client.get("/admin/orgs?page=2")
    assert resp2.status_code == 200
    assert "org2" in resp2.text
    assert "org0" not in resp2.text
    assert "Page 2 of 2" in resp2.text
    assert 'href="?page=1"' in resp2.text


async def test_users_page_paginates(admin_client, monkeypatch):
    from mulchd.auth import create_user

    monkeypatch.setenv("MULCHD_POLICY_DEFAULT_PAGE_SIZE", "2")
    # admin_client already created one user ("admin"); add two more.
    await create_user("bob", "Bob")
    await create_user("carol", "Carol")

    resp = await admin_client.get("/admin/users")
    assert resp.status_code == 200
    assert "Page 1 of 2" in resp.text

    resp2 = await admin_client.get("/admin/users?page=2")
    assert resp2.status_code == 200
    assert "Page 2 of 2" in resp2.text


async def test_memberships_page_paginates_and_preserves_project_filter(admin_client, monkeypatch):
    from mulchd.auth import create_user
    from mulchd.models import Organization, Project, Role, UserMembership

    monkeypatch.setenv("MULCHD_POLICY_DEFAULT_PAGE_SIZE", "2")
    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    for i in range(3):
        user, _ = await create_user(f"user{i}", f"User {i}")
        await UserMembership.create(user=user, project=project, role=Role.READER)

    resp = await admin_client.get("/admin/memberships?project=acme/infra")
    assert resp.status_code == 200
    assert "Page 1 of 2" in resp.text
    assert "project=acme%2Finfra" in resp.text
    assert "page=2" in resp.text


async def test_project_tokens_page_paginates_and_preserves_project_filter(
    admin_client, monkeypatch
):
    from mulchd.auth import create_user
    from mulchd.models import Organization, Project, ProjectToken

    monkeypatch.setenv("MULCHD_POLICY_DEFAULT_PAGE_SIZE", "2")
    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    user, _ = await create_user("bob", "Bob")
    for i in range(3):
        await ProjectToken.create(user=user, project=project, token_hash=f"hash{i}")

    resp = await admin_client.get("/admin/project-tokens?project=acme/infra")
    assert resp.status_code == 200
    assert "Page 1 of 2" in resp.text
    assert "project=acme%2Finfra" in resp.text
    assert "page=2" in resp.text


async def test_pager_hidden_when_everything_fits_on_one_page(admin_client):
    from mulchd.models import Organization

    await Organization.create(slug="acme", display_name="Acme Corp")

    resp = await admin_client.get("/admin/orgs")
    assert resp.status_code == 200
    assert "Page 1 of" not in resp.text
