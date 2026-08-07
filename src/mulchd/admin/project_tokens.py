from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response

from ..models import ProjectToken
from ._shared import admin_page_size, paginate, require_admin, resolve_project, templates

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/project-tokens")
async def project_tokens_page(request: Request, project: str = "", page: int = 1) -> Response:
    qs = ProjectToken.all().order_by("-created_at")
    filtered_project = None
    if project:
        filtered_project = await resolve_project(project)
        if filtered_project:
            qs = qs.filter(project=filtered_project)
    qs = qs.prefetch_related("user", "project", "project__org")
    tokens, total_pages = await paginate(qs, page=page, page_size=admin_page_size())
    return templates.TemplateResponse(
        request,
        "project_tokens.html",
        {
            "active": "project-tokens",
            "tokens": tokens,
            "project_filter": project,
            "filtered_project": filtered_project,
            "page": page,
            "total_pages": total_pages,
        },
    )


@router.post("/project-tokens/{token_id}/revoke")
async def revoke_token(request: Request, token_id: int) -> RedirectResponse:
    await ProjectToken.filter(id=token_id).update(active=False)
    return RedirectResponse("/admin/project-tokens", status_code=303)
