from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from tortoise.exceptions import IntegrityError

from ..admin_grants import (
    grant_superadmin,
    is_last_active_superadmin,
    is_superadmin,
    revoke_superadmin,
)
from ..auth import create_user, generate_token, hash_token
from ..config import settings
from ..instance_events import log_event
from ..models import (
    AdminGrant,
    AdminRole,
    InstanceEventCategory,
    OAuthIdentity,
    User,
)
from ._shared import get_current_admin, require_admin, templates

router = APIRouter(dependencies=[Depends(require_admin)])


async def _render_users(request: Request, *, error: str = "", status_code: int = 200) -> Response:
    users = await User.all().order_by("username")
    return templates.TemplateResponse(
        request,
        "users.html",
        {"active": "users", "users": users, "error": error},
        status_code=status_code,
    )


@router.get("/users")
async def users_page(request: Request, error: str = "") -> Response:
    return await _render_users(request, error=error)


@router.post("/users")
async def create_user_route(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    email: str = Form(default=""),
    admin: User = Depends(get_current_admin),
) -> Response:
    try:
        user, token = await create_user(
            username.strip(),
            display_name.strip(),
            email=email.strip() or None,
        )
    except IntegrityError:
        return await _render_users(
            request, error=f"Username '{username}' is already taken.", status_code=409
        )
    await log_event(InstanceEventCategory.USER_CREATED, actor=admin, subject_user=user)
    request.session["pending_token"] = {
        "username": user.username,
        "display_name": user.display_name,
        "token": token,
    }
    return RedirectResponse("/admin/users/created", status_code=303)


@router.get("/users/created")
async def user_created_page(request: Request) -> Response:
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
async def deactivate_user(
    request: Request, user_id: int, admin: User = Depends(get_current_admin)
) -> Response:
    user = await User.filter(id=user_id).first()
    if user is None:
        return Response(status_code=404)
    if await is_last_active_superadmin(user):
        return RedirectResponse(f"/admin/users/{user_id}?error=last_admin", status_code=303)
    await User.filter(id=user_id).update(active=False)
    await log_event(InstanceEventCategory.USER_DEACTIVATED, actor=admin, subject_user=user)
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/activate")
async def activate_user(request: Request, user_id: int) -> RedirectResponse:
    await User.filter(id=user_id).update(active=True)
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/users/{user_id}")
async def user_detail(request: Request, user_id: int) -> Response:
    user = await User.filter(id=user_id).first()
    if user is None:
        return Response(status_code=404)
    identities = await OAuthIdentity.filter(user=user).order_by("created_at").all()
    return templates.TemplateResponse(
        request,
        "user_detail.html",
        {
            "active": "users",
            "user": user,
            "identities": identities,
            "is_superadmin_user": await is_superadmin(user),
            "error": request.query_params.get("error", ""),
        },
    )


@router.post("/users/{user_id}/grant-admin")
async def grant_admin_route(
    request: Request, user_id: int, granter: User = Depends(get_current_admin)
) -> Response:
    user = await User.filter(id=user_id).first()
    if user is None:
        return Response(status_code=404)
    await grant_superadmin(user, granted_by=granter)
    return RedirectResponse(f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/revoke-admin")
async def revoke_admin_route(
    request: Request, user_id: int, revoker: User = Depends(get_current_admin)
) -> Response:
    grant = await AdminGrant.filter(
        user_id=user_id, role=AdminRole.SUPERADMIN, org=None
    ).first()
    if grant is None:
        return Response(status_code=404)
    ok = await revoke_superadmin(grant, revoked_by=revoker)
    if not ok:
        return RedirectResponse(
            f"/admin/users/{user_id}?error=last_admin", status_code=303
        )
    return RedirectResponse(f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/reset-token")
async def reset_user_token(
    request: Request, user_id: int, admin: User = Depends(get_current_admin)
) -> Response:
    user = await User.filter(id=user_id).first()
    if user is None:
        return Response(status_code=404)
    token = generate_token()
    await User.filter(id=user_id).update(token_hash=hash_token(token))
    await log_event(InstanceEventCategory.TOKEN_RESET, actor=admin, subject_user=user)
    request.session["pending_token"] = {
        "username": user.username,
        "display_name": user.display_name,
        "token": token,
    }
    return RedirectResponse("/admin/users/created", status_code=303)


@router.post("/users/{user_id}/identities/{identity_id}/unlink")
async def unlink_identity(request: Request, user_id: int, identity_id: int) -> Response:
    await OAuthIdentity.filter(id=identity_id, user_id=user_id).delete()
    return RedirectResponse(f"/admin/users/{user_id}", status_code=303)
