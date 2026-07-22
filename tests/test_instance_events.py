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


async def test_log_event_creates_row(db):
    from mulchd.auth import create_user
    from mulchd.instance_events import log_event
    from mulchd.models import InstanceEvent, InstanceEventCategory

    actor, _ = await create_user("erin", "Erin")
    target, _ = await create_user("frank", "Frank")

    await log_event(
        InstanceEventCategory.ADMIN_GRANTED, actor=actor, subject_user=target
    )

    event = await InstanceEvent.get(category=InstanceEventCategory.ADMIN_GRANTED)
    assert event.actor_id == actor.id
    assert event.subject_user_id == target.id


async def test_describe_event_admin_granted(db):
    from mulchd.auth import create_user
    from mulchd.instance_events import describe_event
    from mulchd.models import InstanceEvent, InstanceEventCategory

    actor, _ = await create_user("grace", "Grace")
    target, _ = await create_user("henry", "Henry")
    event = await InstanceEvent.create(
        category=InstanceEventCategory.ADMIN_GRANTED, actor=actor, subject_user=target
    )
    await event.fetch_related("actor", "subject_user")

    assert describe_event(event) == "Granted SUPERADMIN to henry"


async def test_describe_event_admin_revoked(db):
    from mulchd.auth import create_user
    from mulchd.instance_events import describe_event
    from mulchd.models import InstanceEvent, InstanceEventCategory

    actor, _ = await create_user("iris", "Iris")
    target, _ = await create_user("jack", "Jack")
    event = await InstanceEvent.create(
        category=InstanceEventCategory.ADMIN_REVOKED, actor=actor, subject_user=target
    )
    await event.fetch_related("actor", "subject_user")

    assert describe_event(event) == "Revoked SUPERADMIN from jack"


async def test_describe_event_membership_added(db):
    from mulchd.auth import create_user
    from mulchd.instance_events import describe_event
    from mulchd.models import InstanceEvent, InstanceEventCategory, Organization, Project

    actor, _ = await create_user("kate", "Kate")
    target, _ = await create_user("liam", "Liam")
    org = await Organization.create(slug="acme", display_name="Acme")
    project = await Project.create(slug="infra", display_name="Infra", org=org)
    event = await InstanceEvent.create(
        category=InstanceEventCategory.MEMBERSHIP_ADDED,
        actor=actor,
        subject_user=target,
        project=project,
        detail={"role": "writer"},
    )
    await event.fetch_related("actor", "subject_user", "project", "project__org")

    assert describe_event(event) == "Added liam to acme/infra as writer"


async def test_describe_event_membership_removed(db):
    from mulchd.auth import create_user
    from mulchd.instance_events import describe_event
    from mulchd.models import InstanceEvent, InstanceEventCategory, Organization, Project

    actor, _ = await create_user("mia", "Mia")
    target, _ = await create_user("noah", "Noah")
    org = await Organization.create(slug="acme", display_name="Acme")
    project = await Project.create(slug="infra", display_name="Infra", org=org)
    event = await InstanceEvent.create(
        category=InstanceEventCategory.MEMBERSHIP_REMOVED,
        actor=actor,
        subject_user=target,
        project=project,
    )
    await event.fetch_related("actor", "subject_user", "project", "project__org")

    assert describe_event(event) == "Removed noah from acme/infra"


async def test_describe_event_first_login_with_provider(db):
    from mulchd.auth import create_user
    from mulchd.instance_events import describe_event
    from mulchd.models import InstanceEvent, InstanceEventCategory

    user, _ = await create_user("olivia", "Olivia")
    event = await InstanceEvent.create(
        category=InstanceEventCategory.FIRST_LOGIN,
        actor=user,
        subject_user=user,
        detail={"provider": "github"},
    )
    await event.fetch_related("actor", "subject_user")

    assert describe_event(event) == "First login (github)"


async def test_describe_event_oauth_linked(db):
    from mulchd.auth import create_user
    from mulchd.instance_events import describe_event
    from mulchd.models import InstanceEvent, InstanceEventCategory

    user, _ = await create_user("peter", "Peter")
    event = await InstanceEvent.create(
        category=InstanceEventCategory.OAUTH_LINKED,
        actor=user,
        subject_user=user,
        detail={"provider": "oidc"},
    )
    await event.fetch_related("actor", "subject_user")

    assert describe_event(event) == "Linked oidc identity"


async def test_describe_event_token_reset(db):
    from mulchd.auth import create_user
    from mulchd.instance_events import describe_event
    from mulchd.models import InstanceEvent, InstanceEventCategory

    actor, _ = await create_user("quinn", "Quinn")
    target, _ = await create_user("ruth", "Ruth")
    event = await InstanceEvent.create(
        category=InstanceEventCategory.TOKEN_RESET, actor=actor, subject_user=target
    )
    await event.fetch_related("actor", "subject_user")

    assert describe_event(event) == "Reset global token for ruth"


async def test_describe_event_org_created(db):
    from mulchd.auth import create_user
    from mulchd.instance_events import describe_event
    from mulchd.models import InstanceEvent, InstanceEventCategory

    actor, _ = await create_user("sam", "Sam")
    event = await InstanceEvent.create(
        category=InstanceEventCategory.ORG_CREATED, actor=actor, detail={"org_slug": "acme"}
    )
    await event.fetch_related("actor")

    assert describe_event(event) == "Created org acme"


async def test_describe_event_project_created(db):
    from mulchd.auth import create_user
    from mulchd.instance_events import describe_event
    from mulchd.models import InstanceEvent, InstanceEventCategory, Organization, Project

    actor, _ = await create_user("tara", "Tara")
    org = await Organization.create(slug="acme", display_name="Acme")
    project = await Project.create(slug="infra", display_name="Infra", org=org)
    event = await InstanceEvent.create(
        category=InstanceEventCategory.PROJECT_CREATED, actor=actor, project=project
    )
    await event.fetch_related("actor", "project", "project__org")

    assert describe_event(event) == "Created project acme/infra"


async def test_describe_event_user_created(db):
    from mulchd.auth import create_user
    from mulchd.instance_events import describe_event
    from mulchd.models import InstanceEvent, InstanceEventCategory

    actor, _ = await create_user("uma", "Uma")
    target, _ = await create_user("victor", "Victor")
    event = await InstanceEvent.create(
        category=InstanceEventCategory.USER_CREATED, actor=actor, subject_user=target
    )
    await event.fetch_related("actor", "subject_user")

    assert describe_event(event) == "Created user victor"


async def test_describe_event_user_deactivated(db):
    from mulchd.auth import create_user
    from mulchd.instance_events import describe_event
    from mulchd.models import InstanceEvent, InstanceEventCategory

    actor, _ = await create_user("wendy", "Wendy")
    target, _ = await create_user("xavier", "Xavier")
    event = await InstanceEvent.create(
        category=InstanceEventCategory.USER_DEACTIVATED, actor=actor, subject_user=target
    )
    await event.fetch_related("actor", "subject_user")

    assert describe_event(event) == "Deactivated user xavier"


async def test_describe_event_invite_created(db):
    from mulchd.auth import create_user
    from mulchd.instance_events import describe_event
    from mulchd.models import InstanceEvent, InstanceEventCategory, Organization, Project

    actor, _ = await create_user("yara", "Yara")
    org = await Organization.create(slug="acme", display_name="Acme")
    project = await Project.create(slug="infra", display_name="Infra", org=org)
    event = await InstanceEvent.create(
        category=InstanceEventCategory.INVITE_CREATED,
        actor=actor,
        project=project,
        detail={"role": "writer"},
    )
    await event.fetch_related("actor", "project", "project__org")

    assert describe_event(event) == "Created invite link for acme/infra (writer)"


async def test_describe_event_invite_revoked(db):
    from mulchd.auth import create_user
    from mulchd.instance_events import describe_event
    from mulchd.models import InstanceEvent, InstanceEventCategory, Organization, Project

    actor, _ = await create_user("zoe", "Zoe")
    org = await Organization.create(slug="acme", display_name="Acme")
    project = await Project.create(slug="infra", display_name="Infra", org=org)
    event = await InstanceEvent.create(
        category=InstanceEventCategory.INVITE_REVOKED, actor=actor, project=project
    )
    await event.fetch_related("actor", "project", "project__org")

    assert describe_event(event) == "Revoked invite link for acme/infra"
