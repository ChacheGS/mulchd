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
