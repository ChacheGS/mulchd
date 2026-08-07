from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from tortoise.exceptions import IntegrityError

from ..instance_events import log_event
from ..models import InstanceEventCategory, Organization, Project, User
from ._shared import admin_page_size, get_current_admin, is_valid_slug, paginate, require_admin, templates

router = APIRouter(dependencies=[Depends(require_admin)])

_PICK_FOR_LABELS = {
    "records": "Records",
    "record-activity": "Record activity",
    "quality": "Quality",
}


async def _render_orgs(
    request: Request, *, error: str = "", status_code: int = 200, pick_for: str = "", page: int = 1
) -> Response:
    qs = Organization.all().order_by("slug").prefetch_related("projects")
    orgs, total_pages = await paginate(qs, page=page, page_size=admin_page_size())
    pick_for_label = _PICK_FOR_LABELS.get(pick_for, "")
    return templates.TemplateResponse(
        request,
        "orgs.html",
        {
            "active": "orgs",
            "orgs": orgs,
            "error": error,
            # Empty unless pick_for matched the allowlist above — a bogus
            # value must never reach the template's URL-building logic.
            "pick_for": pick_for if pick_for_label else "",
            "pick_for_label": pick_for_label,
            "page": page,
            "total_pages": total_pages,
        },
        status_code=status_code,
    )


@router.get("/orgs")
async def orgs_page(request: Request, error: str = "", pick_for: str = "", page: int = 1) -> Response:
    return await _render_orgs(request, error=error, pick_for=pick_for, page=page)


@router.post("/orgs")
async def create_org(
    request: Request,
    slug: str = Form(...),
    display_name: str = Form(...),
    admin: User = Depends(get_current_admin),
) -> Response:
    slug = slug.strip()
    if not is_valid_slug(slug):
        return await _render_orgs(
            request,
            error=f"Org slug '{slug}' must be lowercase letters, numbers, and hyphens only.",
            status_code=422,
        )
    try:
        org = await Organization.create(slug=slug, display_name=display_name.strip())
    except IntegrityError:
        return await _render_orgs(
            request, error=f"Org slug '{slug}' already exists.", status_code=409
        )
    await log_event(InstanceEventCategory.ORG_CREATED, actor=admin, detail={"org_slug": org.slug})
    return RedirectResponse("/admin/orgs", status_code=303)


async def _render_org_detail(
    request: Request,
    org: Organization,
    *,
    error: str = "",
    status_code: int = 200,
    pick_for: str = "",
) -> Response:
    projects = await Project.filter(org=org).order_by("slug")
    pick_for_label = _PICK_FOR_LABELS.get(pick_for, "")
    return templates.TemplateResponse(
        request,
        "org_detail.html",
        {
            "active": "orgs",
            "org": org,
            "projects": projects,
            "error": error,
            "pick_for": pick_for if pick_for_label else "",
            "pick_for_label": pick_for_label,
        },
        status_code=status_code,
    )


@router.get("/orgs/{org_slug}")
async def org_detail_page(
    request: Request, org_slug: str, error: str = "", pick_for: str = ""
) -> Response:
    org = await Organization.get_or_none(slug=org_slug)
    if org is None:
        return Response(status_code=404)
    return await _render_org_detail(request, org, error=error, pick_for=pick_for)


@router.post("/orgs/{org_slug}/projects")
async def create_project(
    request: Request,
    org_slug: str,
    slug: str = Form(...),
    display_name: str = Form(...),
    knowledge_language: str = Form(""),
    admin: User = Depends(get_current_admin),
) -> Response:
    org = await Organization.get_or_none(slug=org_slug)
    if org is None:
        return Response(status_code=404)
    slug = slug.strip()
    if not is_valid_slug(slug):
        return await _render_org_detail(
            request,
            org,
            error=f"Project slug '{slug}' must be lowercase letters, numbers, and hyphens only.",
            status_code=422,
        )
    try:
        project = await Project.create(
            slug=slug,
            display_name=display_name.strip(),
            knowledge_language=knowledge_language.strip() or None,
            org=org,
        )
    except IntegrityError:
        return await _render_org_detail(
            request,
            org,
            error=f"Project slug '{slug}' already exists in that org.",
            status_code=409,
        )
    await log_event(InstanceEventCategory.PROJECT_CREATED, actor=admin, project=project)
    return RedirectResponse(f"/admin/orgs/{org_slug}", status_code=303)
