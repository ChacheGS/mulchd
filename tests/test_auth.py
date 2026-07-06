"""
Tests for the two-tier token auth model.

Global token  — tied to User, used for self-service API (list projects, mint tokens).
Project token — tied to User × Project, used for MCP /sse access.

Role is resolved dynamically from UserMembership at every request, so changes
(membership removal, user deactivation, role change) take effect immediately.
"""

import pytest

from mulchd.auth import (
    _hash_token,
    authenticate_global_token,
    authenticate_project_token,
    create_project_token,
    create_user,
    generate_token,
)
from mulchd.models import (
    Organization,
    Project,
    ProjectToken,
    Role,
    User,
    UserMembership,
)


@pytest.fixture
async def org(db):
    return await Organization.create(slug="acme", display_name="Acme Corp")


@pytest.fixture
async def project(org):
    return await Project.create(slug="infra", display_name="Infrastructure", org=org)


@pytest.fixture
async def user_and_token(db):
    return await create_user("carlos", "Carlos G.")


# ---------------------------------------------------------------------------
# Global token
# ---------------------------------------------------------------------------


async def test_global_token_resolves_active_user(user_and_token):
    user, token = user_and_token
    result = await authenticate_global_token(token)
    assert result is not None
    assert result.id == user.id


async def test_global_token_wrong_token_returns_none(db):
    result = await authenticate_global_token("not-a-real-token")
    assert result is None


async def test_global_token_inactive_user_returns_none(db):
    user, token = await create_user("jorge", "Jorge M.")
    await User.filter(id=user.id).update(active=False)
    result = await authenticate_global_token(token)
    assert result is None


# ---------------------------------------------------------------------------
# Project token — happy path
# ---------------------------------------------------------------------------


async def test_project_token_returns_auth_context(user_and_token, project, org):
    user, _ = user_and_token
    await UserMembership.create(user=user, project=project, role=Role.WRITER)
    _, pt_token = await create_project_token(user, project, label="test")

    ctx = await authenticate_project_token(pt_token)
    assert ctx is not None
    assert ctx.user.id == user.id
    assert ctx.project.id == project.id
    assert ctx.org.id == org.id
    assert ctx.role == Role.WRITER


async def test_project_token_reflects_current_role(user_and_token, project):
    user, _ = user_and_token
    membership = await UserMembership.create(user=user, project=project, role=Role.WRITER)
    _, pt_token = await create_project_token(user, project)

    await UserMembership.filter(id=membership.id).update(role=Role.READER)

    ctx = await authenticate_project_token(pt_token)
    assert ctx is not None
    assert ctx.role == Role.READER  # reflects updated membership, not token creation time


# ---------------------------------------------------------------------------
# Project token — rejection cases
# ---------------------------------------------------------------------------


async def test_project_token_wrong_token_returns_none(db):
    assert await authenticate_project_token("garbage") is None


async def test_project_token_inactive_token_returns_none(user_and_token, project):
    user, _ = user_and_token
    await UserMembership.create(user=user, project=project, role=Role.WRITER)
    pt, pt_token = await create_project_token(user, project)

    await ProjectToken.filter(id=pt.id).update(active=False)

    assert await authenticate_project_token(pt_token) is None


async def test_project_token_inactive_user_returns_none(user_and_token, project):
    user, _ = user_and_token
    await UserMembership.create(user=user, project=project, role=Role.WRITER)
    _, pt_token = await create_project_token(user, project)

    await User.filter(id=user.id).update(active=False)

    assert await authenticate_project_token(pt_token) is None


async def test_project_token_removed_membership_returns_none(user_and_token, project):
    user, _ = user_and_token
    membership = await UserMembership.create(user=user, project=project, role=Role.WRITER)
    _, pt_token = await create_project_token(user, project)

    await membership.delete()

    assert await authenticate_project_token(pt_token) is None


# ---------------------------------------------------------------------------
# Token type separation — global token must not work as project token
# ---------------------------------------------------------------------------


async def test_global_token_rejected_by_project_auth(user_and_token, project):
    """A global (user-level) token must not resolve as a project token."""
    user, global_token = user_and_token
    await UserMembership.create(user=user, project=project, role=Role.WRITER)

    # Global token hash lives in User.token_hash, not ProjectToken.token_hash
    assert await authenticate_project_token(global_token) is None


async def test_project_token_rejected_by_global_auth(user_and_token, project):
    """A project-scoped token must not resolve as a global token."""
    user, _ = user_and_token
    await UserMembership.create(user=user, project=project, role=Role.WRITER)
    _, pt_token = await create_project_token(user, project)

    assert await authenticate_global_token(pt_token) is None


# ---------------------------------------------------------------------------
# Multiple project tokens per user×project
# ---------------------------------------------------------------------------


async def test_multiple_tokens_same_project(user_and_token, project):
    user, _ = user_and_token
    await UserMembership.create(user=user, project=project, role=Role.WRITER)

    _, token_a = await create_project_token(user, project, label="laptop")
    _, token_b = await create_project_token(user, project, label="desktop")

    ctx_a = await authenticate_project_token(token_a)
    ctx_b = await authenticate_project_token(token_b)

    assert ctx_a is not None and ctx_b is not None
    assert ctx_a.user.id == ctx_b.user.id == user.id


async def test_revoking_one_token_leaves_others_active(user_and_token, project):
    user, _ = user_and_token
    await UserMembership.create(user=user, project=project, role=Role.WRITER)

    pt_a, token_a = await create_project_token(user, project, label="laptop")
    _, token_b = await create_project_token(user, project, label="desktop")

    await ProjectToken.filter(id=pt_a.id).update(active=False)

    assert await authenticate_project_token(token_a) is None
    assert await authenticate_project_token(token_b) is not None
