import pytest


async def test_do_bootstrap_creates_admin(db):
    from mulchd.admin_grants import is_superadmin
    from mulchd.cli import _do_bootstrap

    result = await _do_bootstrap("clibootstrap", "CLI Bootstrap", "cli@company.com")

    assert result is not None
    user, token = result
    assert user.username == "clibootstrap"
    assert user.email == "cli@company.com"
    assert isinstance(token, str) and len(token) > 0
    assert await is_superadmin(user) is True


async def test_do_bootstrap_refuses_when_admin_exists(db):
    from mulchd.admin_grants import grant_superadmin
    from mulchd.auth import create_user
    from mulchd.cli import _do_bootstrap

    existing, _ = await create_user("existingadmin2", "Existing")
    await grant_superadmin(existing, granted_by=existing)

    result = await _do_bootstrap("toolate", "Too Late", "toolate@company.com")

    assert result is None


async def test_do_bootstrap_raises_integrity_error_on_username_collision(db):
    from mulchd.auth import create_user
    from mulchd.cli import _do_bootstrap
    from tortoise.exceptions import IntegrityError

    await create_user("taken", "Existing User")

    with pytest.raises(IntegrityError):
        await _do_bootstrap("taken", "Another User", "another@company.com")
