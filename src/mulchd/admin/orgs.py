from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from tortoise.exceptions import IntegrityError

from ..instance_events import log_event
from ..models import InstanceEventCategory, Organization, User
from ._shared import get_current_admin, is_valid_slug, require_admin, templates

router = APIRouter(dependencies=[Depends(require_admin)])


async def _render_orgs(request: Request, *, error: str = "", status_code: int = 200) -> Response:
    orgs = await Organization.all().order_by("slug").prefetch_related("projects")
    return templates.TemplateResponse(
        request,
        "orgs.html",
        {"active": "orgs", "orgs": orgs, "error": error},
        status_code=status_code,
    )


@router.get("/orgs")
async def orgs_page(request: Request, error: str = "") -> Response:
    return await _render_orgs(request, error=error)


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
