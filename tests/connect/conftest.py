import pytest

from mulchd.auth import create_user
from mulchd.models import Organization, Project, UserMembership

# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
async def alice_and_project(db):
    """Returns (user, token, org, project) with a membership."""
    user, token = await create_user("alice", "Alice")
    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="demo", display_name="Demo", org=org)
    await UserMembership.create(user=user, project=project)
    return user, token, org, project


async def _authed_client(client, token: str):
    """Log in and return client (cookie set by side effect)."""
    resp = await client.post(
        "/connect", data={"token": token, "remember_me": ""}, follow_redirects=False
    )
    assert resp.status_code == 303
    return client
