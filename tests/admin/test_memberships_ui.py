import pytest


async def test_add_membership(admin_client):
    await admin_client.post("/admin/orgs", data={"slug": "acme", "display_name": "Acme"})
    from mulchd.models import Organization

    org = await Organization.get(slug="acme")
    await admin_client.post(
        "/admin/projects",
        data={"org_id": org.id, "slug": "proj", "display_name": "Proj"},
    )
    await admin_client.post("/admin/users", data={"username": "jorge", "display_name": "Jorge M."})

    from mulchd.models import Project, User

    user = await User.get(username="jorge")
    project = await Project.get(slug="proj")

    resp = await admin_client.post(
        "/admin/memberships",
        data={"user_id": user.id, "project_id": project.id, "role": "writer"},
        follow_redirects=False,
    )
    assert resp.status_code == 303


async def test_add_membership_logs_event(admin_client):
    from mulchd.auth import create_user
    from mulchd.models import InstanceEvent, InstanceEventCategory, Organization, Project

    target, _ = await create_user("memberadd", "Member Add")
    org = await Organization.create(slug="acme", display_name="Acme")
    project = await Project.create(slug="infra", display_name="Infra", org=org)

    resp = await admin_client.post(
        "/admin/memberships",
        data={"user_id": target.id, "project_id": project.id, "role": "writer"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    event = await InstanceEvent.get(category=InstanceEventCategory.MEMBERSHIP_ADDED)
    assert event.subject_user_id == target.id
    assert event.project_id == project.id
    assert event.detail == {"role": "writer"}


async def test_remove_membership_logs_event(admin_client):
    from mulchd.auth import create_user
    from mulchd.models import (
        InstanceEvent,
        InstanceEventCategory,
        Organization,
        Project,
        Role,
        UserMembership,
    )

    target, _ = await create_user("memberremove", "Member Remove")
    org = await Organization.create(slug="acme2", display_name="Acme2")
    project = await Project.create(slug="infra2", display_name="Infra2", org=org)
    membership = await UserMembership.create(user=target, project=project, role=Role.WRITER)

    resp = await admin_client.post(
        f"/admin/memberships/{membership.id}/remove", follow_redirects=False
    )
    assert resp.status_code == 303

    event = await InstanceEvent.get(category=InstanceEventCategory.MEMBERSHIP_REMOVED)
    assert event.subject_user_id == target.id
    assert event.project_id == project.id


async def test_duplicate_membership_does_not_log(admin_client):
    from mulchd.auth import create_user
    from mulchd.models import InstanceEvent, InstanceEventCategory, Organization, Project

    target, _ = await create_user("memberdup", "Member Dup")
    org = await Organization.create(slug="acmedup", display_name="AcmeDup")
    project = await Project.create(slug="infradup", display_name="InfraDup", org=org)

    await admin_client.post(
        "/admin/memberships",
        data={"user_id": target.id, "project_id": project.id, "role": "writer"},
    )
    resp = await admin_client.post(
        "/admin/memberships",
        data={"user_id": target.id, "project_id": project.id, "role": "writer"},
        follow_redirects=False,
    )
    assert resp.status_code == 409

    count = await InstanceEvent.filter(category=InstanceEventCategory.MEMBERSHIP_ADDED).count()
    assert count == 1


async def test_remove_nonexistent_membership_does_not_log(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory

    resp = await admin_client.post("/admin/memberships/999999/remove", follow_redirects=False)
    assert resp.status_code == 303

    count = await InstanceEvent.filter(category=InstanceEventCategory.MEMBERSHIP_REMOVED).count()
    assert count == 0


async def test_memberships_page_filters_by_project(admin_client):
    from mulchd.models import Organization, Project, Role, User, UserMembership

    org = await Organization.create(slug="acme", display_name="Acme")
    proj_a = await Project.create(slug="infra", display_name="Infra", org=org)
    proj_b = await Project.create(slug="web", display_name="Web", org=org)
    alice = await User.create(username="alice", display_name="Alice", token_hash="h1")
    bob = await User.create(username="bob", display_name="Bob", token_hash="h2")
    await UserMembership.create(user=alice, project=proj_a, role=Role.WRITER)
    await UserMembership.create(user=bob, project=proj_b, role=Role.WRITER)

    resp = await admin_client.get("/admin/memberships?project=acme/infra")
    assert resp.status_code == 200
    # Membership rows render the username in its own monospace span; the
    # Add-membership form's user dropdown always lists every active user
    # (by design) as a plain <option>, so scope the assertion to the row
    # markup rather than the raw page text.
    assert '<span class="monospace">alice</span>' in resp.text
    assert '<span class="monospace">bob</span>' not in resp.text
    assert "Filtered to" in resp.text
    # bob is still offered in the Add-membership form's user dropdown.
    assert '<option value="{}"'.format(bob.id) in resp.text


async def test_memberships_page_unfiltered_shows_everyone(admin_client):
    from mulchd.models import Organization, Project, Role, User, UserMembership

    org = await Organization.create(slug="acme", display_name="Acme")
    proj_a = await Project.create(slug="infra", display_name="Infra", org=org)
    proj_b = await Project.create(slug="web", display_name="Web", org=org)
    alice = await User.create(username="alice", display_name="Alice", token_hash="h1")
    bob = await User.create(username="bob", display_name="Bob", token_hash="h2")
    await UserMembership.create(user=alice, project=proj_a, role=Role.WRITER)
    await UserMembership.create(user=bob, project=proj_b, role=Role.WRITER)

    resp = await admin_client.get("/admin/memberships")
    assert resp.status_code == 200
    assert "alice" in resp.text
    assert "bob" in resp.text
    assert "Filtered to" not in resp.text
