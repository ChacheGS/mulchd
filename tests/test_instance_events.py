async def test_instance_event_create(db):
    from mulchd.auth import create_user
    from mulchd.models import InstanceEvent, InstanceEventCategory

    actor, _ = await create_user("alice", "Alice")
    target, _ = await create_user("bob", "Bob")

    event = await InstanceEvent.create(
        category=InstanceEventCategory.ADMIN_GRANTED,
        actor=actor,
        subject_user=target,
    )

    assert event.category == InstanceEventCategory.ADMIN_GRANTED
    assert event.actor_id == actor.id
    assert event.subject_user_id == target.id
    assert event.project_id is None
    assert event.detail is None


async def test_instance_event_with_project_and_detail(db):
    from mulchd.auth import create_user
    from mulchd.models import InstanceEvent, InstanceEventCategory, Organization, Project

    actor, _ = await create_user("carol", "Carol")
    org = await Organization.create(slug="acme", display_name="Acme")
    project = await Project.create(slug="infra", display_name="Infra", org=org)

    event = await InstanceEvent.create(
        category=InstanceEventCategory.PROJECT_CREATED,
        actor=actor,
        project=project,
        detail={"slug": "infra"},
    )

    assert event.project_id == project.id
    assert event.detail == {"slug": "infra"}


async def test_user_first_login_at_defaults_none(db):
    from mulchd.auth import create_user

    user, _ = await create_user("dave", "Dave")

    assert user.first_login_at is None
