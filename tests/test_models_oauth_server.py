from typing import Any

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


async def test_oauth_client_roundtrip(db):
    from mulchd.models import OAuthClient

    client = await OAuthClient.create(
        client_id="client-1",
        client_metadata={"client_name": "Claude Desktop", "redirect_uris": ["http://localhost/cb"]},
    )
    fetched = await OAuthClient.filter(client_id="client-1").first()
    assert fetched is not None
    assert fetched.id == client.id
    assert fetched.client_metadata["client_name"] == "Claude Desktop"


async def test_oauth_client_id_unique(db):
    from mulchd.models import OAuthClient
    from tortoise.exceptions import IntegrityError

    await OAuthClient.create(client_id="dup", client_metadata={})
    with pytest.raises(IntegrityError):
        await OAuthClient.create(client_id="dup", client_metadata={})


async def test_oauth_grant_unique_per_client_and_user(db):
    from mulchd.auth import create_user
    from mulchd.models import OAuthClient, OAuthGrant, Organization, Project
    from tortoise.exceptions import IntegrityError

    user, _ = await create_user("alice", "Alice")
    org = await Organization.create(slug="acme", display_name="Acme")
    project = await Project.create(slug="demo", display_name="Demo", org=org)
    client = await OAuthClient.create(client_id="client-2", client_metadata={})

    await OAuthGrant.create(client=client, user=user, project=project)
    with pytest.raises(IntegrityError):
        await OAuthGrant.create(client=client, user=user, project=project)


async def test_oauth_code_and_token_link_to_grant(db):
    from datetime import UTC, datetime, timedelta

    from mulchd.auth import create_user
    from mulchd.models import OAuthClient, OAuthCode, OAuthGrant, OAuthToken, Organization, Project

    user, _ = await create_user("bob", "Bob")
    org = await Organization.create(slug="acme2", display_name="Acme2")
    project = await Project.create(slug="demo2", display_name="Demo2", org=org)
    client = await OAuthClient.create(client_id="client-3", client_metadata={})
    grant = await OAuthGrant.create(client=client, user=user, project=project)

    code = await OAuthCode.create(
        code_hash="hash1",
        client_id=client.client_id,
        grant=grant,
        redirect_uri="http://localhost/cb",
        code_challenge="challenge",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    assert (await code.grant).id == grant.id

    token = await OAuthToken.create(
        access_token_hash="acc-hash",
        refresh_token_hash="ref-hash",
        client_id=client.client_id,
        grant=grant,
        access_expires_at=datetime.now(UTC) + timedelta(hours=1),
        refresh_expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    assert (await token.grant).id == grant.id


async def test_oauth_code_hash_unique(db):
    from datetime import UTC, datetime, timedelta

    from mulchd.auth import create_user
    from mulchd.models import OAuthClient, OAuthCode, OAuthGrant, Organization, Project
    from tortoise.exceptions import IntegrityError

    user, _ = await create_user("carol", "Carol")
    org = await Organization.create(slug="acme3", display_name="Acme3")
    project = await Project.create(slug="demo3", display_name="Demo3", org=org)
    client = await OAuthClient.create(client_id="client-4", client_metadata={})
    grant = await OAuthGrant.create(client=client, user=user, project=project)
    kwargs: dict[str, Any] = dict(
        code_hash="dup-code-hash",
        client_id=client.client_id,
        grant=grant,
        redirect_uri="http://localhost/cb",
        code_challenge="challenge",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    await OAuthCode.create(**kwargs)
    with pytest.raises(IntegrityError):
        await OAuthCode.create(**kwargs)


async def test_oauth_token_hashes_unique(db):
    from datetime import UTC, datetime, timedelta

    from mulchd.auth import create_user
    from mulchd.models import OAuthClient, OAuthGrant, OAuthToken, Organization, Project
    from tortoise.exceptions import IntegrityError

    user, _ = await create_user("dave", "Dave")
    org = await Organization.create(slug="acme4", display_name="Acme4")
    project = await Project.create(slug="demo4", display_name="Demo4", org=org)
    client = await OAuthClient.create(client_id="client-5", client_metadata={})
    grant = await OAuthGrant.create(client=client, user=user, project=project)
    now = datetime.now(UTC)

    await OAuthToken.create(
        access_token_hash="dup-access-hash",
        refresh_token_hash="ref-hash-a",
        client_id=client.client_id,
        grant=grant,
        access_expires_at=now + timedelta(hours=1),
        refresh_expires_at=now + timedelta(days=30),
    )
    with pytest.raises(IntegrityError):
        await OAuthToken.create(
            access_token_hash="dup-access-hash",
            refresh_token_hash="ref-hash-b",
            client_id=client.client_id,
            grant=grant,
            access_expires_at=now + timedelta(hours=1),
            refresh_expires_at=now + timedelta(days=30),
        )

    await OAuthToken.create(
        access_token_hash="access-hash-c",
        refresh_token_hash="dup-refresh-hash",
        client_id=client.client_id,
        grant=grant,
        access_expires_at=now + timedelta(hours=1),
        refresh_expires_at=now + timedelta(days=30),
    )
    with pytest.raises(IntegrityError):
        await OAuthToken.create(
            access_token_hash="access-hash-d",
            refresh_token_hash="dup-refresh-hash",
            client_id=client.client_id,
            grant=grant,
            access_expires_at=now + timedelta(hours=1),
            refresh_expires_at=now + timedelta(days=30),
        )


async def test_oauth_grant_granted_role_defaults_to_admin(db):
    """Pre-existing/no-op grant creation must keep today's behavior (no ceiling),
    so the default has to be the top of the rank, not WRITER or READER."""
    from mulchd.auth import create_user
    from mulchd.models import OAuthClient, OAuthGrant, Organization, Project, Role

    user, _ = await create_user("erin", "Erin")
    org = await Organization.create(slug="acme6", display_name="Acme6")
    project = await Project.create(slug="demo6", display_name="Demo6", org=org)
    client = await OAuthClient.create(client_id="client-6", client_metadata={})

    grant = await OAuthGrant.create(client=client, user=user, project=project)
    assert grant.granted_role == Role.ADMIN


async def test_oauth_grant_granted_role_explicit_value_roundtrips(db):
    from mulchd.auth import create_user
    from mulchd.models import OAuthClient, OAuthGrant, Organization, Project, Role

    user, _ = await create_user("frank", "Frank")
    org = await Organization.create(slug="acme7", display_name="Acme7")
    project = await Project.create(slug="demo7", display_name="Demo7", org=org)
    client = await OAuthClient.create(client_id="client-7", client_metadata={})

    grant = await OAuthGrant.create(client=client, user=user, project=project, granted_role=Role.READER)
    fetched = await OAuthGrant.get(id=grant.id)
    assert fetched.granted_role == Role.READER
