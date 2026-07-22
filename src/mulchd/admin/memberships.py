from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response
from tortoise.exceptions import IntegrityError

from ..instance_events import log_event
from ..models import InstanceEventCategory, Project, Role, User, UserMembership
from ._shared import get_admin_user, is_admin, redirect_login, templates

router = APIRouter()


@router.get("/memberships")
async def memberships_page(request: Request, user: str = "", error: str = "") -> Response:
    if not await is_admin(request):
        return redirect_login()
    memberships = await UserMembership.all().prefetch_related("user", "project", "project__org")
    users = await User.filter(active=True).order_by("username")
    projects = await Project.all().order_by("slug").prefetch_related("org")
    return templates.TemplateResponse(
        request,
        "memberships.html",
        {
            "active": "memberships",
            "memberships": memberships,
            "users": users,
            "projects": projects,
            "roles": list(Role),
            "preselect_user": user,
            "error": error,
        },
    )


@router.post("/memberships")
async def add_membership(
    request: Request,
    user_id: int = Form(...),
    project_id: int = Form(...),
    role: str = Form(...),
) -> Response:
    admin = await get_admin_user(request)
    if admin is None:
        return redirect_login()
    user = await User.get_or_none(id=user_id)
    project = await Project.get_or_none(id=project_id)
    if user is None or project is None:
        return RedirectResponse("/admin/memberships", status_code=303)
    try:
        await UserMembership.create(user=user, project=project, role=Role(role))
    except IntegrityError:
        memberships = await UserMembership.all().prefetch_related("user", "project", "project__org")
        users = await User.filter(active=True).order_by("username")
        projects = await Project.all().order_by("slug").prefetch_related("org")
        return templates.TemplateResponse(
            request,
            "memberships.html",
            {
                "active": "memberships",
                "memberships": memberships,
                "users": users,
                "projects": projects,
                "roles": list(Role),
                "preselect_user": "",
                "error": f"{user.username} already has access to that project.",
            },
            status_code=409,
        )
    await log_event(
        InstanceEventCategory.MEMBERSHIP_ADDED,
        actor=admin,
        subject_user=user,
        project=project,
        detail={"role": role},
    )
    return RedirectResponse("/admin/memberships", status_code=303)


@router.post("/memberships/{membership_id}/remove")
async def remove_membership(request: Request, membership_id: int) -> Response:
    admin = await get_admin_user(request)
    if admin is None:
        return redirect_login()
    membership = (
        await UserMembership.filter(id=membership_id).select_related("user", "project").first()
    )
    if membership is not None:
        await UserMembership.filter(id=membership_id).delete()
        await log_event(
            InstanceEventCategory.MEMBERSHIP_REMOVED,
            actor=admin,
            subject_user=membership.user,
            project=membership.project,
        )
    return RedirectResponse("/admin/memberships", status_code=303)
