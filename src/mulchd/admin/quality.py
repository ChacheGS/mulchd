from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ..domains import mulch_dir
from ..models import Project
from ..mulch import audit_corpus
from ._shared import require_admin, resolve_project, templates

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/quality")
async def quality_page(request: Request, project: str = "", domain: str = "") -> Response:
    projects = await Project.all().prefetch_related("org").order_by("org__slug", "slug")
    selected_project = None
    report: dict = {}
    suggestions: list[dict] = []

    if project:
        selected_project = await resolve_project(project)
        if selected_project:
            m_dir = mulch_dir(selected_project.org.slug, selected_project.slug)
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
