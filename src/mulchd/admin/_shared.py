from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

# Templates live at src/mulchd/templates/, one level above this package.
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


def is_admin(request: Request) -> bool:
    return bool(request.session.get("admin"))


def redirect_login() -> RedirectResponse:
    return RedirectResponse("/admin/login", status_code=303)
