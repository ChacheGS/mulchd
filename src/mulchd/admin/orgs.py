from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response
from tortoise.exceptions import IntegrityError

from ..models import Organization
from ._shared import is_admin, redirect_login, templates

router = APIRouter()


@router.get("/orgs")
async def orgs_page(request: Request, error: str = "") -> Response:
    if not is_admin(request):
        return redirect_login()
    orgs = await Organization.all().order_by("slug").prefetch_related("projects")
    return templates.TemplateResponse(
        request,
        "orgs.html",
        {"active": "orgs", "orgs": orgs, "error": error},
    )


@router.post("/orgs")
async def create_org(
    request: Request,
    slug: str = Form(...),
    display_name: str = Form(...),
) -> Response:
    if not is_admin(request):
        return redirect_login()
    try:
        await Organization.create(slug=slug.strip(), display_name=display_name.strip())
    except IntegrityError:
        orgs = await Organization.all().order_by("slug").prefetch_related("projects")
        return templates.TemplateResponse(
            request,
            "orgs.html",
            {
                "active": "orgs",
                "orgs": orgs,
                "error": f"Org slug '{slug}' already exists.",
            },
            status_code=409,
        )
    return RedirectResponse("/admin/orgs", status_code=303)
