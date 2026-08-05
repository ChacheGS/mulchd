from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ..domains import list_domain_names, mulch_dir
from ..mulch import audit_corpus
from ._shared import (
    require_admin,
    resolve_project_by_slugs,
    set_last_project_cookie,
    templates,
)

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/p/{org_slug}/{project_slug}/quality")
async def quality_page(
    request: Request, org_slug: str, project_slug: str, domain: str = ""
) -> Response:
    project = await resolve_project_by_slugs(org_slug, project_slug)
    if project is None:
        return Response(status_code=404)

    available_domains = list_domain_names(org_slug, project_slug)
    # A domain that doesn't currently exist (typo, or removed since page load)
    # must never reach `ml` — that's what previously caused an unhandled
    # MulchError -> 500. Silently drop it back to "no filter" instead.
    domain_filter = domain if domain in available_domains else ""

    m_dir = mulch_dir(org_slug, project_slug)
    result = await audit_corpus(m_dir, domain=domain_filter or None)
    report = result.get("report", {})
    suggestions = result.get("suggestions", {}).get("groups", [])

    response = templates.TemplateResponse(
        request,
        "quality.html",
        {
            "active": "quality",
            "project": project,
            "active_tab": "quality",
            "tab_path": "quality",
            "available_domains": available_domains,
            "filter_domain": domain_filter,
            "report": report,
            "suggestions": suggestions,
        },
    )
    set_last_project_cookie(response, org_slug, project_slug)
    return response
