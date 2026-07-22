from datetime import UTC, datetime

from tortoise import transactions

from .config import settings
from .instance_events import log_event
from .models import AdminGrant, AdminRole, InstanceEventCategory, User


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
    existing = await AdminGrant.filter(
        user=user, role=AdminRole.SUPERADMIN, org=None, revoked_at=None
    ).first()
    if existing is not None:
        return existing
    grant = await AdminGrant.create(
        user=user, role=AdminRole.SUPERADMIN, granted_by=granted_by
    )
    await log_event(
        InstanceEventCategory.ADMIN_GRANTED, actor=granted_by, subject_user=user
    )
    return grant


async def maybe_bootstrap_admin(user: User) -> bool:
    """
    If MULCHD_BOOTSTRAP_ADMIN_EMAIL is set, matches user's email, and zero
    active SUPERADMIN grants exist anywhere, grant user SUPERADMIN
    (self-referential granted_by). Returns True if a grant was created.
    Once any grant exists, this becomes permanently inert regardless of
    whether the setting is still present in config.
    """
    if not settings.bootstrap_admin_email:
        return False
    if not user.email or user.email.lower() != settings.bootstrap_admin_email.lower():
        return False
    if await active_superadmin_count() > 0:
        return False
    await grant_superadmin(user, granted_by=user)
    return True


async def revoke_superadmin(grant: AdminGrant, revoked_by: User) -> bool:
    """
    Soft-revoke an active grant. Returns False (no-op) if already revoked,
    or if it's the last active SUPERADMIN grant — never leave zero admins.

    Re-fetches the grant under a row lock (like invite._claim_invite) so two
    concurrent revokes of the last two admins can't both read "not last" and
    both proceed, which would leave the instance with zero admins.
    """
    async with transactions.in_transaction():
        fresh = await AdminGrant.select_for_update().get(id=grant.id)
        if fresh.revoked_at is not None:
            return False
        await fresh.fetch_related("user")
        if await is_last_active_superadmin(fresh.user):
            return False
        fresh.revoked_by = revoked_by
        fresh.revoked_at = datetime.now(UTC).replace(tzinfo=None)
        await fresh.save()
    await log_event(
        InstanceEventCategory.ADMIN_REVOKED, actor=revoked_by, subject_user=fresh.user
    )
    return True
