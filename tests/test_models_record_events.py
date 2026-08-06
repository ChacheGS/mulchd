"""
RecordEvent / RecordEdit model tests.
"""

import uuid

import pytest
from tortoise.exceptions import IntegrityError

from mulchd.models import Organization, Project, RecordEdit, RecordEvent, User


async def test_record_event_actor_delete_restricted(db):
    """RecordEvent is an audit log; deleting its actor must not silently
    cascade-delete the audit trail (on_delete=RESTRICT, not the Tortoise
    default CASCADE)."""
    org = await Organization.create(slug="acme", display_name="Acme")
    project = await Project.create(slug="infra", display_name="Infra", org=org)
    user = await User.create(username="carlos", display_name="Carlos", token_hash="h1")

    await RecordEvent.create(
        record_id="mx-abc123",
        project=project,
        domain="infra",
        actor=user,
        action="write",
        session_id=uuid.uuid4(),
    )

    with pytest.raises(IntegrityError):
        await user.delete()

    assert await RecordEvent.filter(record_id="mx-abc123").count() == 1


async def test_record_edit_actor_delete_restricted(db):
    """Same guarantee for RecordEdit's before-snapshot audit rows."""
    org = await Organization.create(slug="acme", display_name="Acme")
    project = await Project.create(slug="infra", display_name="Infra", org=org)
    user = await User.create(username="carlos", display_name="Carlos", token_hash="h1")

    await RecordEdit.create(
        record_id="mx-abc123",
        project=project,
        domain="infra",
        actor=user,
        before_snapshot={"title": "old"},
        session_id=uuid.uuid4(),
    )

    with pytest.raises(IntegrityError):
        await user.delete()

    assert await RecordEdit.filter(record_id="mx-abc123").count() == 1
