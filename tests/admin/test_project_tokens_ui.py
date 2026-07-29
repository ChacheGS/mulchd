import pytest


async def test_project_tokens_page_requires_auth(client):
    resp = await client.get("/admin/project-tokens", follow_redirects=False)
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


async def test_project_tokens_page_renders(admin_client):
    from mulchd.models import Organization, Project, ProjectToken, User

    org = await Organization.create(slug="acme", display_name="Acme")
    project = await Project.create(slug="demo", display_name="Demo", org=org)
    user = await User.create(username="tokenowner", display_name="Token Owner", token_hash="h-tok1")
    await ProjectToken.create(user=user, project=project, token_hash="th-1", label="CI token")

    resp = await admin_client.get("/admin/project-tokens")
    assert resp.status_code == 200
    assert "CI token" in resp.text


async def test_revoke_token_action_requires_auth(client):
    resp = await client.post("/admin/project-tokens/1/revoke", follow_redirects=False)
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


async def test_revoke_token_action_deactivates_token(admin_client):
    from mulchd.models import Organization, Project, ProjectToken, User

    org = await Organization.create(slug="acme", display_name="Acme")
    project = await Project.create(slug="demo", display_name="Demo", org=org)
    user = await User.create(username="tokenowner2", display_name="Token Owner", token_hash="h-tok2")
    token = await ProjectToken.create(user=user, project=project, token_hash="th-2", label="CI token")

    resp = await admin_client.post(
        f"/admin/project-tokens/{token.id}/revoke", follow_redirects=False
    )
    assert resp.status_code == 303
    assert "/admin/project-tokens" in resp.headers["location"]

    await token.refresh_from_db()
    assert token.active is False
