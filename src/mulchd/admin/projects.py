from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response
from tortoise.exceptions import IntegrityError

from ..instance_events import log_event
from ..models import (
    InstanceEventCategory,
    InviteLink,
    InviteUse,
    Organization,
    Project,
    Role,
)
from ._shared import get_admin_user, is_admin, redirect_login, templates

router = APIRouter()


@router.get("/projects")
async def projects_page(request: Request, error: str = "") -> Response:
    if not await is_admin(request):
        return redirect_login()
    projects = await Project.all().order_by("slug").prefetch_related("org")
    orgs = await Organization.all().order_by("slug")
    return templates.TemplateResponse(
        request,
        "projects.html",
        {"active": "projects", "projects": projects, "orgs": orgs, "error": error},
    )


@router.get("/projects/{project_id}")
async def project_detail_page(request: Request, project_id: int) -> Response:
    if not await is_admin(request):
        return redirect_login()
    project = await Project.filter(id=project_id).select_related("org").first()
    if project is None:
        return Response(status_code=404)
    invites = (
        await InviteLink.filter(project=project)
        .select_related("created_by")
        .order_by("-created_at")
        .all()
    )
    uses_by_invite: dict[int, list] = {inv.id: [] for inv in invites}
    if invites:
        uses = (
            await InviteUse.filter(invite_id__in=[inv.id for inv in invites])
            .select_related("user")
            .order_by("used_at")
            .all()
        )
        for use in uses:
            uses_by_invite[use.invite_id].append(use)
    return templates.TemplateResponse(
        request,
        "project_detail.html",
        {
            "active": "projects",
            "project": project,
            "invites": invites,
            "uses_by_invite": uses_by_invite,
            "roles": list(Role),
        },
    )


@router.post("/projects")
async def create_project(
    request: Request,
    org_id: int = Form(...),
    slug: str = Form(...),
    display_name: str = Form(...),
    knowledge_language: str = Form(""),
) -> Response:
    admin = await get_admin_user(request)
    if admin is None:
        return redirect_login()
    org = await Organization.get_or_none(id=org_id)
    if org is None:
        return RedirectResponse("/admin/projects", status_code=303)
    try:
        project = await Project.create(
            slug=slug.strip(),
            display_name=display_name.strip(),
            knowledge_language=knowledge_language.strip() or None,
            org=org,
        )
    except IntegrityError:
        projects = await Project.all().order_by("slug").prefetch_related("org")
        orgs = await Organization.all().order_by("slug")
        return templates.TemplateResponse(
            request,
            "projects.html",
            {
                "active": "projects",
                "projects": projects,
                "orgs": orgs,
                "error": f"Project slug '{slug}' already exists in that org.",
            },
            status_code=409,
        )
    await log_event(InstanceEventCategory.PROJECT_CREATED, actor=admin, project=project)
    return RedirectResponse("/admin/projects", status_code=303)


@router.post("/projects/{project_id}/language")
async def set_project_language(
    request: Request,
    project_id: int,
    knowledge_language: str = Form(""),
) -> Response:
    if not await is_admin(request):
        return redirect_login()
    project = await Project.get_or_none(id=project_id)
    if project is None:
        return RedirectResponse("/admin/projects", status_code=303)
    project.knowledge_language = knowledge_language.strip() or None
    await project.save(update_fields=["knowledge_language"])
    return RedirectResponse("/admin/projects", status_code=303)
