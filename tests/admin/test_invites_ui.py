import pytest


async def test_create_invite_link(admin_client):
    from mulchd.models import InviteLink, Organization, Project, User
    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    resp = await admin_client.post(
        f"/admin/projects/{project.id}/invites",
        data={"role": "writer", "max_uses": "5", "expires_in": "3600", "allowed_email_domains": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    invite = await InviteLink.get(project=project)
    assert resp.headers["location"] == f"/admin/projects/{project.id}?new_token={invite.token}"
    assert invite.role == "writer"
    assert invite.max_uses == 5
    assert invite.expires_at is not None
    admin_user = await User.filter(username="admin").first()
    assert invite.created_by_id == admin_user.id


async def test_revoke_invite_link(admin_client):
    from mulchd.models import InviteLink, Organization, Project
    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    invite = await InviteLink.create(
        token="revoketest123",
        project=project,
        role="writer",
    )
    resp = await admin_client.post(f"/admin/invites/{invite.id}/revoke", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/admin/projects/{project.id}"
    await invite.refresh_from_db()
    assert invite.revoked is True


async def test_create_invite_logs_event(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory, Organization, Project

    org = await Organization.create(slug="loginviteorg", display_name="Log Invite Org")
    project = await Project.create(slug="loginviteproj", display_name="Log Invite Proj", org=org)
    resp = await admin_client.post(
        f"/admin/projects/{project.id}/invites",
        data={"role": "writer", "max_uses": "", "expires_in": "", "allowed_email_domains": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    event = await InstanceEvent.get(category=InstanceEventCategory.INVITE_CREATED)
    assert event.project_id == project.id
    assert event.detail == {"role": "writer"}


async def test_revoke_invite_logs_event(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory, InviteLink, Organization, Project

    org = await Organization.create(slug="logrevokeorg", display_name="Log Revoke Org")
    project = await Project.create(slug="logrevokeproj", display_name="Log Revoke Proj", org=org)
    invite = await InviteLink.create(token="logrevoketoken", project=project, role="writer")

    resp = await admin_client.post(
        f"/admin/invites/{invite.id}/revoke", follow_redirects=False
    )
    assert resp.status_code == 303

    event = await InstanceEvent.get(category=InstanceEventCategory.INVITE_REVOKED)
    assert event.project_id == project.id
