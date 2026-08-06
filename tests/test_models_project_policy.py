"""
ProjectPolicy model tests.
"""

import pytest
from tortoise.exceptions import IntegrityError

from mulchd.models import Organization, Project, ProjectPolicy, User


async def test_project_policy_unique_per_project_and_key(db):
    org = await Organization.create(slug="acme", display_name="Acme")
    project = await Project.create(slug="infra", display_name="Infra", org=org)
    user = await User.create(username="carlos", display_name="Carlos", token_hash="h1")

    await ProjectPolicy.create(project=project, key="guardrail_enforcement", value=["enforce"])

    with pytest.raises(IntegrityError):
        await ProjectPolicy.create(project=project, key="guardrail_enforcement", value=["warn"])

    # A different project can use the same key.
    other = await Project.create(slug="ops", display_name="Ops", org=org)
    await ProjectPolicy.create(project=other, key="guardrail_enforcement", value=["warn"])

    row = await ProjectPolicy.get(project=project, key="guardrail_enforcement")
    assert row.value == ["enforce"]

    row.updated_by = user
    await row.save(update_fields=["updated_by_id"])
    await row.fetch_related("updated_by")
    assert row.updated_by.username == "carlos"


async def test_project_policy_survives_updated_by_user_deletion(db):
    """Deleting the User who last touched a policy must not delete the policy row.

    updated_by is on_delete=SET_NULL, not the Tortoise-default CASCADE: losing
    attribution is fine, silently discarding the project's actual override value
    is not.
    """
    org = await Organization.create(slug="acme", display_name="Acme")
    project = await Project.create(slug="infra", display_name="Infra", org=org)
    user = await User.create(username="carlos", display_name="Carlos", token_hash="h1")

    policy = await ProjectPolicy.create(
        project=project,
        key="guardrail_enforcement",
        value=["enforce"],
        updated_by=user,
    )

    await user.delete()

    row = await ProjectPolicy.get(id=policy.id)
    assert row.value == ["enforce"]
    assert row.updated_by_id is None
