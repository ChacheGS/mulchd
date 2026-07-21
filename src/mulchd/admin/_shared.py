from importlib.metadata import version as _pkg_version
from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from ..admin_grants import is_superadmin
from ..connect import _get_connect_user_id
from ..models import User

# Templates live at src/mulchd/templates/, one level above this package.
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
templates.env.globals["mulchd_version"] = _pkg_version("mulchd")


async def get_admin_user(request: Request) -> User | None:
    """Resolve the authenticated User for this request, if they hold an active SUPERADMIN grant."""
    user_id = _get_connect_user_id(request)
    if user_id is None:
        return None
    user = await User.filter(id=user_id, active=True).first()
    if user is None:
        return None
    if not await is_superadmin(user):
        return None
    return user


async def is_admin(request: Request) -> bool:
    return await get_admin_user(request) is not None


def redirect_login() -> RedirectResponse:
    return RedirectResponse("/connect", status_code=303)
