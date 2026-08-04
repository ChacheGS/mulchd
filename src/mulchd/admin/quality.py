from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ..domains import mulch_dir
from ..models import Project
from ..mulch import audit_corpus
from ._shared import require_admin, resolve_project_by_slugs, set_last_project_cookie, templates

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/p/{org_slug}/{project_slug}/quality")
async def quality_page(
    request: Request, org_slug: str, project_slug: str, domain: str = ""
) -> Response:
    project = await resolve_project_by_slugs(org_slug, project_slug)
    if project is None:
        return Response(status_code=404)

    m_dir = mulch_dir(org_slug, project_slug)
    result = await audit_corpus(m_dir, domain=domain or None)
    report = result.get("report", {})
    suggestions = result.get("suggestions", {}).get("groups", [])

    all_projects = await Project.all().order_by("org__slug", "slug").prefetch_related("org")
    response = templates.TemplateResponse(
        request,
        "quality.html",
        {
            "active": "quality",
            "project": project,
            "all_projects": all_projects,
            "active_tab": "quality",
            "tab_path": "quality",
            "filter_domain": domain,
            "report": report,
            "suggestions": suggestions,
        },
    )
    set_last_project_cookie(response, org_slug, project_slug)
    return response
