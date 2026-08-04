from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from tortoise.exceptions import IntegrityError

from ..instance_events import log_event
from ..models import InstanceEventCategory, Project, Role, User, UserMembership
from ._shared import get_current_admin, require_admin, resolve_project, templates

router = APIRouter(dependencies=[Depends(require_admin)])


async def _render_memberships(
    request: Request,
    *,
    preselect_user: str = "",
    error: str = "",
    status_code: int = 200,
    project_filter: str = "",
) -> Response:
    qs = UserMembership.all()
    filtered_project = None
    if project_filter:
        filtered_project = await resolve_project(project_filter)
        if filtered_project:
            qs = qs.filter(project=filtered_project)
    memberships = await qs.prefetch_related("user", "project", "project__org")
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
            "preselect_user": preselect_user,
            "error": error,
            "project_filter": project_filter,
            "filtered_project": filtered_project,
        },
        status_code=status_code,
    )


@router.get("/memberships")
async def memberships_page(
    request: Request, user: str = "", error: str = "", project: str = ""
) -> Response:
    return await _render_memberships(request, preselect_user=user, error=error, project_filter=project)


@router.post("/memberships")
async def add_membership(
    request: Request,
    user_id: int = Form(...),
    project_id: int = Form(...),
    role: str = Form(...),
    admin: User = Depends(get_current_admin),
) -> Response:
    user = await User.get_or_none(id=user_id)
    project = await Project.get_or_none(id=project_id)
    if user is None or project is None:
        return RedirectResponse("/admin/memberships", status_code=303)
    try:
        await UserMembership.create(user=user, project=project, role=Role(role))
    except IntegrityError:
        return await _render_memberships(
            request,
            error=f"{user.username} already has access to that project.",
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
async def remove_membership(
    request: Request, membership_id: int, admin: User = Depends(get_current_admin)
) -> Response:
    membership = (
        await UserMembership.filter(id=membership_id).select_related("user", "project").first()
    )
    if membership is not None:
        await membership.delete()
        await log_event(
            InstanceEventCategory.MEMBERSHIP_REMOVED,
            actor=admin,
            subject_user=membership.user,
            project=membership.project,
        )
    return RedirectResponse("/admin/memberships", status_code=303)
