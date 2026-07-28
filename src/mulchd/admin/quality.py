from fastapi import APIRouter, Request
from fastapi.responses import Response

from ..domains import mulch_dir
from ..models import Project
from ..mulch import audit_corpus
from ._shared import is_admin, redirect_login, templates

router = APIRouter()


@router.get("/quality")
async def quality_page(request: Request, project: str = "", domain: str = "") -> Response:
    if not await is_admin(request):
        return redirect_login()

    projects = await Project.all().prefetch_related("org").order_by("org__slug", "slug")
    selected_project = None
    report: dict = {}
    suggestions: list[dict] = []

    if project and "/" in project:
        org_slug, project_slug = project.split("/", 1)
        selected_project = (
            await Project.filter(slug=project_slug, org__slug=org_slug)
            .prefetch_related("org")
            .first()
        )
        if selected_project:
            m_dir = mulch_dir(org_slug, project_slug)
            result = await audit_corpus(m_dir, domain=domain or None)
            report = result.get("report", {})
            suggestions = result.get("suggestions", {}).get("groups", [])

    return templates.TemplateResponse(
        request,
        "quality.html",
        {
            "active": "quality",
            "projects": projects,
            "selected": project,
            "selected_project": selected_project,
            "filter_domain": domain,
            "report": report,
            "suggestions": suggestions,
        },
    )
