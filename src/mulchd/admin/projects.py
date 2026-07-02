from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response
from tortoise.exceptions import IntegrityError

from ..models import Organization, Project
from ._shared import is_admin, redirect_login, templates

router = APIRouter()


@router.get("/projects")
async def projects_page(request: Request, error: str = "") -> Response:
    if not is_admin(request):
        return redirect_login()
    projects = await Project.all().order_by("slug").prefetch_related("org")
    orgs = await Organization.all().order_by("slug")
    return templates.TemplateResponse(
        request,
        "projects.html",
        {"active": "projects", "projects": projects, "orgs": orgs, "error": error},
    )


@router.post("/projects")
async def create_project(
    request: Request,
    org_id: int = Form(...),
    slug: str = Form(...),
    display_name: str = Form(...),
    knowledge_language: str = Form(""),
) -> Response:
    if not is_admin(request):
        return redirect_login()
    org = await Organization.get_or_none(id=org_id)
    if org is None:
        return RedirectResponse("/admin/projects", status_code=303)
    try:
        await Project.create(
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
    return RedirectResponse("/admin/projects", status_code=303)


@router.post("/projects/{project_id}/language")
async def set_project_language(
    request: Request,
    project_id: int,
    knowledge_language: str = Form(""),
) -> Response:
    if not is_admin(request):
        return redirect_login()
    project = await Project.get_or_none(id=project_id)
    if project is None:
        return RedirectResponse("/admin/projects", status_code=303)
    project.knowledge_language = knowledge_language.strip() or None
    await project.save(update_fields=["knowledge_language"])
    return RedirectResponse("/admin/projects", status_code=303)
