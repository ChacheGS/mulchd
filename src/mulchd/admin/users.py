from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response
from tortoise.exceptions import IntegrityError

from ..auth import create_user
from ..config import settings
from ..models import User
from ._shared import is_admin, redirect_login, templates

router = APIRouter()


@router.get("/users")
async def users_page(request: Request, error: str = "") -> Response:
    if not is_admin(request):
        return redirect_login()
    users = await User.all().order_by("username")
    return templates.TemplateResponse(
        request,
        "users.html",
        {"active": "users", "users": users, "error": error},
    )


@router.post("/users")
async def create_user_route(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
) -> Response:
    if not is_admin(request):
        return redirect_login()
    try:
        user, token = await create_user(username.strip(), display_name.strip())
    except IntegrityError:
        users = await User.all().order_by("username")
        return templates.TemplateResponse(
            request,
            "users.html",
            {
                "active": "users",
                "users": users,
                "error": f"Username '{username}' is already taken.",
            },
            status_code=409,
        )
    request.session["pending_token"] = {
        "username": user.username,
        "display_name": user.display_name,
        "token": token,
    }
    return RedirectResponse("/admin/users/created", status_code=303)


@router.get("/users/created")
async def user_created_page(request: Request) -> Response:
    if not is_admin(request):
        return redirect_login()
    pending = request.session.pop("pending_token", None)
    if pending is None:
        return RedirectResponse("/admin/users", status_code=303)
    return templates.TemplateResponse(
        request,
        "user_created.html",
        {
            "active": "users",
            "username": pending["username"],
            "display_name": pending["display_name"],
            "token": pending["token"],
            "server_url": f"http://{settings.host}:{settings.port}",
        },
    )


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(request: Request, user_id: int) -> RedirectResponse:
    if not is_admin(request):
        return redirect_login()
    await User.filter(id=user_id).update(active=False)
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/activate")
async def activate_user(request: Request, user_id: int) -> RedirectResponse:
    if not is_admin(request):
        return redirect_login()
    await User.filter(id=user_id).update(active=True)
    return RedirectResponse("/admin/users", status_code=303)
