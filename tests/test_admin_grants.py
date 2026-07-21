async def test_admin_grant_create(db):
    from mulchd.auth import create_user
    from mulchd.models import AdminGrant, AdminRole

    user, _ = await create_user("alice", "Alice")
    grant = await AdminGrant.create(user=user, granted_by=user)

    assert grant.role == AdminRole.SUPERADMIN
    assert grant.org_id is None
    assert grant.granted_by_id == user.id
    assert grant.revoked_at is None
    assert grant.revoked_by_id is None


async def test_admin_grant_self_referential_granted_by(db):
    """Bootstrap grants set granted_by to the same user — no nullable needed."""
    from mulchd.auth import create_user
    from mulchd.models import AdminGrant

    user, _ = await create_user("bob", "Bob")
    grant = await AdminGrant.create(user=user, granted_by=user)

    assert grant.user_id == grant.granted_by_id


async def test_is_superadmin_true_for_active_grant(db):
    from mulchd.admin_grants import is_superadmin
    from mulchd.auth import create_user
    from mulchd.models import AdminGrant

    user, _ = await create_user("carol", "Carol")
    await AdminGrant.create(user=user, granted_by=user)

    assert await is_superadmin(user) is True


async def test_is_superadmin_false_without_grant(db):
    from mulchd.admin_grants import is_superadmin
    from mulchd.auth import create_user

    user, _ = await create_user("dave", "Dave")

    assert await is_superadmin(user) is False


async def test_is_superadmin_false_after_revoke(db):
    from mulchd.admin_grants import is_superadmin
    from mulchd.auth import create_user
    from mulchd.models import AdminGrant

    user, _ = await create_user("erin", "Erin")
    grant = await AdminGrant.create(user=user, granted_by=user)
    grant.revoked_by = user
    from datetime import UTC, datetime
    grant.revoked_at = datetime.now(UTC).replace(tzinfo=None)
    await grant.save()

    assert await is_superadmin(user) is False


async def test_active_superadmin_count(db):
    from mulchd.admin_grants import active_superadmin_count
    from mulchd.auth import create_user
    from mulchd.models import AdminGrant

    assert await active_superadmin_count() == 0

    alice, _ = await create_user("alice2", "Alice")
    bob, _ = await create_user("bob2", "Bob")
    await AdminGrant.create(user=alice, granted_by=alice)
    await AdminGrant.create(user=bob, granted_by=alice)

    assert await active_superadmin_count() == 2


async def test_is_last_active_superadmin(db):
    from mulchd.admin_grants import grant_superadmin, is_last_active_superadmin
    from mulchd.auth import create_user

    alice, _ = await create_user("alice3", "Alice")
    bob, _ = await create_user("bob3", "Bob")
    await grant_superadmin(alice, granted_by=alice)

    assert await is_last_active_superadmin(alice) is True
    assert await is_last_active_superadmin(bob) is False  # bob isn't even an admin

    await grant_superadmin(bob, granted_by=alice)
    assert await is_last_active_superadmin(alice) is False  # no longer the only one


async def test_grant_superadmin(db):
    from mulchd.admin_grants import grant_superadmin, is_superadmin
    from mulchd.auth import create_user

    alice, _ = await create_user("alice4", "Alice")
    bob, _ = await create_user("bob4", "Bob")

    grant = await grant_superadmin(bob, granted_by=alice)

    assert await is_superadmin(bob) is True
    assert grant.granted_by_id == alice.id


async def test_revoke_superadmin_succeeds_when_others_remain(db):
    from mulchd.admin_grants import grant_superadmin, is_superadmin, revoke_superadmin
    from mulchd.auth import create_user

    alice, _ = await create_user("alice5", "Alice")
    bob, _ = await create_user("bob5", "Bob")
    await grant_superadmin(alice, granted_by=alice)
    bob_grant = await grant_superadmin(bob, granted_by=alice)

    ok = await revoke_superadmin(bob_grant, revoked_by=alice)

    assert ok is True
    assert await is_superadmin(bob) is False
    await bob_grant.refresh_from_db()
    assert bob_grant.revoked_by_id == alice.id
    assert bob_grant.revoked_at is not None


async def test_revoke_superadmin_blocked_as_last_admin(db):
    from mulchd.admin_grants import grant_superadmin, is_superadmin, revoke_superadmin
    from mulchd.auth import create_user

    alice, _ = await create_user("alice6", "Alice")
    grant = await grant_superadmin(alice, granted_by=alice)

    ok = await revoke_superadmin(grant, revoked_by=alice)

    assert ok is False
    assert await is_superadmin(alice) is True  # unchanged


async def test_revoke_superadmin_noop_if_already_revoked(db):
    from mulchd.admin_grants import grant_superadmin, revoke_superadmin
    from mulchd.auth import create_user

    alice, _ = await create_user("alice7", "Alice")
    bob, _ = await create_user("bob7", "Bob")
    await grant_superadmin(alice, granted_by=alice)
    bob_grant = await grant_superadmin(bob, granted_by=alice)
    await revoke_superadmin(bob_grant, revoked_by=alice)

    ok_again = await revoke_superadmin(bob_grant, revoked_by=alice)

    assert ok_again is False
