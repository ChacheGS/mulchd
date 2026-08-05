import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

from tests.connect.conftest import _authed_client


async def test_connected_apps_lists_grants(client, alice_and_project):
    """Connected apps are shown on the /connect/projects dashboard, not a
    separate page — there's no standalone /connect/apps route."""
    from mulchd.models import OAuthClient, OAuthGrant

    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    oc = await OAuthClient.create(
        client_id="cli-f",
        client_metadata={
            "client_id": "cli-f",
            "client_name": "Cli F",
            "redirect_uris": ["http://localhost/cb"],
        },
    )
    await OAuthGrant.create(client=oc, user=user, project=project)

    resp = await client.get("/connect/projects")
    assert resp.status_code == 200
    assert "Cli F" in resp.text
    assert project.display_name in resp.text


async def test_connected_apps_revoke_deletes_grant(client, alice_and_project):
    from mulchd.models import OAuthClient, OAuthGrant

    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    oc = await OAuthClient.create(
        client_id="cli-g",
        client_metadata={
            "client_id": "cli-g",
            "client_name": "Cli G",
            "redirect_uris": ["http://localhost/cb"],
        },
    )
    grant = await OAuthGrant.create(client=oc, user=user, project=project)

    resp = await client.post(f"/connect/apps/{grant.id}/revoke", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/connect/projects"
    assert not await OAuthGrant.filter(id=grant.id).exists()


async def test_connected_apps_revoke_other_users_grant_404s(client, alice_and_project):
    from mulchd.auth import create_user
    from mulchd.models import OAuthClient, OAuthGrant

    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    other_user, _ = await create_user("mallory", "Mallory")
    oc = await OAuthClient.create(
        client_id="cli-h",
        client_metadata={
            "client_id": "cli-h",
            "client_name": "Cli H",
            "redirect_uris": ["http://localhost/cb"],
        },
    )
    grant = await OAuthGrant.create(client=oc, user=other_user, project=project)

    resp = await client.post(f"/connect/apps/{grant.id}/revoke")
    assert resp.status_code == 404
    assert await OAuthGrant.filter(id=grant.id).exists()


async def test_connected_apps_revoke_requires_auth(client, alice_and_project):
    from mulchd.models import OAuthClient, OAuthGrant

    user, token, org, project = alice_and_project
    oc = await OAuthClient.create(
        client_id="cli-noauth",
        client_metadata={
            "client_id": "cli-noauth",
            "client_name": "Cli NoAuth",
            "redirect_uris": ["http://localhost/cb"],
        },
    )
    grant = await OAuthGrant.create(client=oc, user=user, project=project)

    resp = await client.post(f"/connect/apps/{grant.id}/revoke", follow_redirects=False)
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]
    assert await OAuthGrant.filter(id=grant.id).exists()


async def test_connected_apps_revoke_forces_full_reconsent(client, alice_and_project):
    """After revoking a grant, the next /connect/oauth-consent GET for that same
    client_id must show the project picker again — not silently fast-path a
    new code the way it does while a grant still exists. This is the mechanism
    the whole 'connected apps' page exists to provide: revoke-to-switch-project."""
    from mulchd.models import OAuthClient, OAuthGrant

    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    oc = await OAuthClient.create(
        client_id="cli-reconsent",
        client_metadata={
            "client_id": "cli-reconsent",
            "client_name": "Cli Reconsent",
            "redirect_uris": ["http://localhost/cb"],
        },
    )
    grant = await OAuthGrant.create(client=oc, user=user, project=project)

    await client.post(f"/connect/apps/{grant.id}/revoke")

    resp = await client.get(
        "/connect/oauth-consent",
        params={
            "client_id": "cli-reconsent",
            "redirect_uri": "http://localhost/cb",
            "code_challenge": "chal",
            "state": "st-reconsent",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "Cli Reconsent" in resp.text
    assert not await OAuthGrant.filter(client=oc, user=user).exists()


async def test_connected_apps_shows_granted_role(client, alice_and_project):
    from mulchd.models import OAuthClient, OAuthGrant, Role

    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    oc = await OAuthClient.create(
        client_id="cli-role-badge",
        client_metadata={
            "client_id": "cli-role-badge",
            "client_name": "Cli RoleBadge",
            "redirect_uris": ["http://localhost/cb"],
        },
    )
    await OAuthGrant.create(client=oc, user=user, project=project, granted_role=Role.READER)

    resp = await client.get("/connect/projects")
    assert resp.status_code == 200
    assert "badge-reader" in resp.text
