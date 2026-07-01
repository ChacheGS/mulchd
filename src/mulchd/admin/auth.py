import hmac

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response

from ..config import settings
from ._shared import is_admin, redirect_login, templates

router = APIRouter()


@router.get("/login")
async def login_page(request: Request) -> Response:
    if is_admin(request):
        return RedirectResponse("/admin/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def login(request: Request, password: str = Form(...)) -> Response:
    if hmac.compare_digest(password, settings.admin_password):
        request.session["admin"] = True
        return RedirectResponse("/admin/", status_code=303)
    return templates.TemplateResponse(
        request, "login.html", {"error": "Incorrect password"}, status_code=401
    )


@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)
