import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

from mulchd.auth import create_project_token, create_user
from tests.connect.conftest import _authed_client

# ── mint ────────────────────────────────────────────────────────────────────


async def test_connect_mint_returns_snippets(client, alice_and_project):
    user, token, *_ = alice_and_project
    await _authed_client(client, token)
    resp = await client.post("/connect/projects/acme/demo/mint", data={"label": "laptop"})
    assert resp.status_code == 200


async def test_connect_mint_creates_token_in_db(client, alice_and_project):
    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    await client.post("/connect/projects/acme/demo/mint", data={"label": "laptop"})
    from mulchd.models import ProjectToken

    count = await ProjectToken.filter(user=user, project=project, active=True).count()
    assert count == 1


# ── revoke ───────────────────────────────────────────────────────────────────


async def test_connect_revoke_token(client, alice_and_project):
    user, token, org, project = alice_and_project
    pt, _ = await create_project_token(user, project, label="old machine")
    await _authed_client(client, token)
    resp = await client.post(f"/connect/projects/acme/demo/revoke/{pt.id}")
    assert resp.status_code == 200
    await pt.refresh_from_db()
    assert pt.active is False


async def test_connect_revoke_wrong_user_404(client, alice_and_project):
    user, token, org, project = alice_and_project
    # Create a second user and their token
    bob, _ = await create_user("bob", "Bob")
    pt, _ = await create_project_token(bob, project, label="bobs laptop")
    await _authed_client(client, token)  # logged in as alice
    resp = await client.post(f"/connect/projects/acme/demo/revoke/{pt.id}")
    assert resp.status_code == 404
