import uuid

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


async def test_record_meta_same_record_id_allowed_across_projects(db):
    """ml's record IDs are content-derived (a hash of type + an identifying
    field), not random, so two different projects can legitimately produce
    the same record_id. RecordMeta uniqueness is per (project, record_id),
    not on record_id alone."""
    from mulchd.models import Organization, Project, RecordMeta, User

    org = await Organization.create(slug="acme", display_name="Acme")
    project_a = await Project.create(slug="a", display_name="A", org=org)
    project_b = await Project.create(slug="b", display_name="B", org=org)
    user = await User.create(username="carlos", display_name="Carlos G.", token_hash="h1")

    await RecordMeta.create(
        record_id="mx-dupe123",
        project=project_a,
        domain="infra",
        author=user,
        session_id=uuid.uuid4(),
    )
    await RecordMeta.create(
        record_id="mx-dupe123",
        project=project_b,
        domain="pipelines",
        author=user,
        session_id=uuid.uuid4(),
    )

    assert await RecordMeta.filter(record_id="mx-dupe123").count() == 2


async def test_record_meta_unique_per_project_and_record_id(db):
    from tortoise.exceptions import IntegrityError

    from mulchd.models import Organization, Project, RecordMeta, User

    org = await Organization.create(slug="acme", display_name="Acme")
    project = await Project.create(slug="infra", display_name="Infra", org=org)
    user = await User.create(username="carlos", display_name="Carlos G.", token_hash="h1")

    await RecordMeta.create(
        record_id="mx-abc123",
        project=project,
        domain="infra",
        author=user,
        session_id=uuid.uuid4(),
    )
    with pytest.raises(IntegrityError):
        await RecordMeta.create(
            record_id="mx-abc123",
            project=project,
            domain="infra",
            author=user,
            session_id=uuid.uuid4(),
        )
