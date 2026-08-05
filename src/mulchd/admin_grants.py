from tortoise import transactions
from tortoise.exceptions import DoesNotExist, IntegrityError

from .config import settings
from .instance_events import log_event
from .models import AdminGrant, AdminRole, InstanceEventCategory, User


async def is_superadmin(user: User) -> bool:
    """Does user currently hold an active, instance-wide SUPERADMIN grant?"""
    return await AdminGrant.filter(user=user, role=AdminRole.SUPERADMIN, org=None).exists()


async def active_superadmin_count() -> int:
    """How many active, instance-wide SUPERADMIN grants exist right now."""
    return await AdminGrant.filter(role=AdminRole.SUPERADMIN, org=None).count()


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
    """
    Grant user an active, instance-wide SUPERADMIN role. Idempotent: if user
    already holds one, returns the existing grant without creating a
    duplicate or logging a second event.

    Relies on AdminGrant's (user, role) unique constraint rather than a
    check-then-create — two concurrent calls for the same user can both pass
    the "not superadmin yet" read, but only one INSERT wins; the loser
    catches IntegrityError and re-fetches instead of racing to create a
    duplicate row. Assumes autocommit (no caller wraps this in an outer
    transaction) — under an outer transaction, Postgres would abort it on
    the integrity violation and the re-fetch below would fail too.
    """
    existing = await AdminGrant.filter(user=user, role=AdminRole.SUPERADMIN, org=None).first()
    if existing is not None:
        return existing
    try:
        grant = await AdminGrant.create(
            user=user, role=AdminRole.SUPERADMIN, granted_by=granted_by
        )
    except IntegrityError:
        return await AdminGrant.get(user=user, role=AdminRole.SUPERADMIN, org=None)
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
    Revoke an active grant (deletes the row — InstanceEvent is the audit
    trail now, so there's nothing left to soft-revoke). Returns False
    (no-op) if the grant no longer exists, or if it's the last active SUPERADMIN
    grant — never leave zero admins.

    Re-fetches the grant under a row lock (like invite.claim_invite) so two
    concurrent revokes of the last two admins can't both read "not last" and
    both proceed, which would leave the instance with zero admins.
    """
    async with transactions.in_transaction():
        try:
            fresh = await AdminGrant.select_for_update().get(id=grant.id)
        except DoesNotExist:
            return False
        await fresh.fetch_related("user")
        if await is_last_active_superadmin(fresh.user):
            return False
        subject_user = fresh.user
        await fresh.delete()
    await log_event(
        InstanceEventCategory.ADMIN_REVOKED, actor=revoked_by, subject_user=subject_user
    )
    return True
