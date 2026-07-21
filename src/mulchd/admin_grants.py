from datetime import UTC, datetime

from .models import AdminGrant, AdminRole, User


async def is_superadmin(user: User) -> bool:
    """Does user currently hold an active, instance-wide SUPERADMIN grant?"""
    return await AdminGrant.filter(
        user=user, role=AdminRole.SUPERADMIN, org=None, revoked_at=None
    ).exists()


async def active_superadmin_count() -> int:
    """How many active, instance-wide SUPERADMIN grants exist right now."""
    return await AdminGrant.filter(
        role=AdminRole.SUPERADMIN, org=None, revoked_at=None
    ).count()


async def is_last_active_superadmin(user: User) -> bool:
    """
    True if user holds an active SUPERADMIN grant and is the only one —
    i.e. removing their access (by revoking the grant or deactivating the
    account) would leave the instance with zero admins.
    """
    if not await is_superadmin(user):
        return False
    return await active_superadmin_count() <= 1


async def grant_superadmin(user: User, granted_by: User) -> AdminGrant:
    return await AdminGrant.create(
        user=user, role=AdminRole.SUPERADMIN, granted_by=granted_by
    )


async def revoke_superadmin(grant: AdminGrant, revoked_by: User) -> bool:
    """
    Soft-revoke an active grant. Returns False (no-op) if already revoked,
    or if it's the last active SUPERADMIN grant — never leave zero admins.
    """
    if grant.revoked_at is not None:
        return False
    await grant.fetch_related("user")
    if await is_last_active_superadmin(grant.user):
        return False
    grant.revoked_by = revoked_by
    grant.revoked_at = datetime.now(UTC).replace(tzinfo=None)
    await grant.save()
    return True
