import argparse
import asyncio

from tortoise import Tortoise
from tortoise.exceptions import IntegrityError

from .admin_grants import active_superadmin_count, grant_superadmin
from .auth import create_user
from .config import TORTOISE_ORM
from .models import User


async def _do_bootstrap(
    username: str, display_name: str, email: str
) -> tuple[User, str] | None:
    """
    Create the first admin User and grant SUPERADMIN, self-referentially.
    Returns None (refuses) if any active SUPERADMIN grant already exists —
    this is a bootstrap tool, not a general "make someone admin" tool.
    """
    if await active_superadmin_count() > 0:
        return None
    user, token = await create_user(username, display_name, email=email)
    await grant_superadmin(user, granted_by=user)
    return user, token


async def _bootstrap_admin_main(username: str, display_name: str, email: str) -> None:
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        try:
            result = await _do_bootstrap(username, display_name, email)
        except IntegrityError:
            print(f"Refusing: username '{username}' or email '{email}' is already taken.")
            return
        if result is None:
            print(
                "Refusing: an active SUPERADMIN grant already exists. "
                "Use the admin UI to grant further access."
            )
            return
        user, token = result
        print(f"Created admin user '{user.username}' with SUPERADMIN access.")
        print(f"Global token (shown once): {token}")
    finally:
        await Tortoise.close_connections()


def bootstrap_admin() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap the first mulchd admin (fallback for non-OAuth deployments)."
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    asyncio.run(
        _bootstrap_admin_main(args.username, args.display_name, args.email)
    )
