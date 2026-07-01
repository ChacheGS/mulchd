"""
Integration tests for the self-service REST API.

All endpoints require a global (user-level) bearer token.
Project-scoped tokens are rejected at this layer.
"""

import pytest

from mulchd.auth import create_project_token, create_user
from mulchd.models import Organization, Project, ProjectToken, Role, UserMembership


@pytest.fixture
async def org(db):
    return await Organization.create(slug="acme", display_name="Acme Corp")


@pytest.fixture
async def infra(org):
    return await Project.create(slug="infra", display_name="Infrastructure", org=org)


@pytest.fixture
async def data_proj(org):
    return await Project.create(slug="data", display_name="Data Platform", org=org)


@pytest.fixture
async def carlos_and_token(db):
    return await create_user("carlos", "Carlos G.")


@pytest.fixture
async def jorge_and_token(db):
    return await create_user("jorge", "Jorge M.")


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# GET /api/me/projects
# ---------------------------------------------------------------------------


async def test_list_projects_returns_memberships(client, carlos_and_token, infra, data_proj):
    user, token = carlos_and_token
    await UserMembership.create(user=user, project=infra, role=Role.WRITER)
    await UserMembership.create(user=user, project=data_proj, role=Role.READER)

    resp = await client.get("/api/me/projects", headers=auth(token))
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    slugs = {i["project"]["slug"] for i in items}
    assert slugs == {"infra", "data"}
    roles = {i["project"]["slug"]: i["role"] for i in items}
    assert roles["infra"] == "writer"
    assert roles["data"] == "reader"


async def test_list_projects_empty_for_user_with_no_memberships(client, carlos_and_token):
    _, token = carlos_and_token
    resp = await client.get("/api/me/projects", headers=auth(token))
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_projects_only_own_memberships(client, carlos_and_token, jorge_and_token, infra):
    carlos, carlos_token = carlos_and_token
    jorge, jorge_token = jorge_and_token
    await UserMembership.create(user=jorge, project=infra, role=Role.WRITER)

    resp = await client.get("/api/me/projects", headers=auth(carlos_token))
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_projects_rejects_project_token(client, carlos_and_token, infra):
    user, token = carlos_and_token
    await UserMembership.create(user=user, project=infra, role=Role.WRITER)
    _, pt_token = await create_project_token(user, infra)

    resp = await client.get("/api/me/projects", headers=auth(pt_token))
    assert resp.status_code == 401


async def test_list_projects_rejects_invalid_token(client):
    resp = await client.get("/api/me/projects", headers=auth("garbage"))
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/projects/{org}/{project}/tokens
# ---------------------------------------------------------------------------


async def test_mint_token_returns_raw_token_once(client, carlos_and_token, infra):
    user, token = carlos_and_token
    await UserMembership.create(user=user, project=infra, role=Role.WRITER)

    resp = await client.post(
        "/api/projects/acme/infra/tokens",
        json={"label": "laptop"},
        headers=auth(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "token" in body
    assert len(body["token"]) > 20
    assert body["label"] == "laptop"
    assert "id" in body
    assert "created_at" in body


async def test_mint_token_empty_label(client, carlos_and_token, infra):
    user, token = carlos_and_token
    await UserMembership.create(user=user, project=infra, role=Role.WRITER)

    resp = await client.post(
        "/api/projects/acme/infra/tokens",
        json={"label": ""},
        headers=auth(token),
    )
    assert resp.status_code == 201
    assert resp.json()["label"] == ""


async def test_mint_token_creates_usable_project_token(client, carlos_and_token, infra):
    from mulchd.auth import authenticate_project_token

    user, token = carlos_and_token
    await UserMembership.create(user=user, project=infra, role=Role.WRITER)

    resp = await client.post(
        "/api/projects/acme/infra/tokens", json={"label": "ci"}, headers=auth(token)
    )
    raw = resp.json()["token"]
    ctx = await authenticate_project_token(raw)
    assert ctx is not None
    assert ctx.user.id == user.id
    assert ctx.project.id == infra.id


async def test_mint_token_forbidden_for_non_member(client, carlos_and_token, infra):
    _, token = carlos_and_token
    resp = await client.post(
        "/api/projects/acme/infra/tokens", json={"label": "x"}, headers=auth(token)
    )
    assert resp.status_code == 403


async def test_mint_token_project_not_found(client, carlos_and_token):
    _, token = carlos_and_token
    resp = await client.post(
        "/api/projects/acme/nonexistent/tokens", json={"label": "x"}, headers=auth(token)
    )
    assert resp.status_code == 404


async def test_mint_token_rejects_project_token(client, carlos_and_token, infra):
    user, token = carlos_and_token
    await UserMembership.create(user=user, project=infra, role=Role.WRITER)
    _, pt_token = await create_project_token(user, infra)

    resp = await client.post(
        "/api/projects/acme/infra/tokens", json={"label": "x"}, headers=auth(pt_token)
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/projects/{org}/{project}/tokens
# ---------------------------------------------------------------------------


async def test_list_tokens_returns_active_tokens(client, carlos_and_token, infra):
    user, token = carlos_and_token
    await UserMembership.create(user=user, project=infra, role=Role.WRITER)
    await create_project_token(user, infra, label="laptop")
    await create_project_token(user, infra, label="desktop")

    resp = await client.get("/api/projects/acme/infra/tokens", headers=auth(token))
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    labels = {i["label"] for i in items}
    assert labels == {"laptop", "desktop"}


async def test_list_tokens_excludes_revoked(client, carlos_and_token, infra):
    user, token = carlos_and_token
    await UserMembership.create(user=user, project=infra, role=Role.WRITER)
    pt, _ = await create_project_token(user, infra, label="old")
    await create_project_token(user, infra, label="active")
    await ProjectToken.filter(id=pt.id).update(active=False)

    resp = await client.get("/api/projects/acme/infra/tokens", headers=auth(token))
    items = resp.json()
    assert len(items) == 1
    assert items[0]["label"] == "active"


async def test_list_tokens_excludes_other_users_tokens(
    client, carlos_and_token, jorge_and_token, infra
):
    carlos, carlos_token = carlos_and_token
    jorge, jorge_token = jorge_and_token
    await UserMembership.create(user=carlos, project=infra, role=Role.WRITER)
    await UserMembership.create(user=jorge, project=infra, role=Role.WRITER)
    await create_project_token(jorge, infra, label="jorge-laptop")

    resp = await client.get("/api/projects/acme/infra/tokens", headers=auth(carlos_token))
    assert resp.json() == []


async def test_list_tokens_no_hash_in_response(client, carlos_and_token, infra):
    user, token = carlos_and_token
    await UserMembership.create(user=user, project=infra, role=Role.WRITER)
    await create_project_token(user, infra, label="x")

    resp = await client.get("/api/projects/acme/infra/tokens", headers=auth(token))
    item = resp.json()[0]
    assert "token" not in item
    assert "token_hash" not in item


# ---------------------------------------------------------------------------
# DELETE /api/projects/{org}/{project}/tokens/{id}
# ---------------------------------------------------------------------------


async def test_revoke_token_deactivates_it(client, carlos_and_token, infra):
    from mulchd.auth import authenticate_project_token

    user, token = carlos_and_token
    await UserMembership.create(user=user, project=infra, role=Role.WRITER)
    pt, pt_raw = await create_project_token(user, infra, label="to-revoke")

    resp = await client.delete(
        f"/api/projects/acme/infra/tokens/{pt.id}", headers=auth(token)
    )
    assert resp.status_code == 204
    assert await authenticate_project_token(pt_raw) is None


async def test_revoke_token_not_found(client, carlos_and_token, infra):
    user, token = carlos_and_token
    await UserMembership.create(user=user, project=infra, role=Role.WRITER)

    resp = await client.delete("/api/projects/acme/infra/tokens/9999", headers=auth(token))
    assert resp.status_code == 404


async def test_revoke_token_cannot_revoke_other_users_token(
    client, carlos_and_token, jorge_and_token, infra
):
    carlos, carlos_token = carlos_and_token
    jorge, _ = jorge_and_token
    await UserMembership.create(user=carlos, project=infra, role=Role.WRITER)
    await UserMembership.create(user=jorge, project=infra, role=Role.WRITER)
    pt, _ = await create_project_token(jorge, infra, label="jorge-token")

    resp = await client.delete(
        f"/api/projects/acme/infra/tokens/{pt.id}", headers=auth(carlos_token)
    )
    assert resp.status_code == 404


async def test_revoke_already_revoked_token(client, carlos_and_token, infra):
    user, token = carlos_and_token
    await UserMembership.create(user=user, project=infra, role=Role.WRITER)
    pt, _ = await create_project_token(user, infra)
    await ProjectToken.filter(id=pt.id).update(active=False)

    resp = await client.delete(
        f"/api/projects/acme/infra/tokens/{pt.id}", headers=auth(token)
    )
    assert resp.status_code == 404
