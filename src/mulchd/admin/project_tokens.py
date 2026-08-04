from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response

from ..models import ProjectToken
from ._shared import require_admin, resolve_project, templates

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/project-tokens")
async def project_tokens_page(request: Request, project: str = "") -> Response:
    qs = ProjectToken.all()
    filtered_project = None
    if project:
        filtered_project = await resolve_project(project)
        if filtered_project:
            qs = qs.filter(project=filtered_project)
    tokens = await qs.prefetch_related("user", "project", "project__org").order_by("-created_at")
    return templates.TemplateResponse(
        request,
        "project_tokens.html",
        {
            "active": "project-tokens",
            "tokens": tokens,
            "project_filter": project,
            "filtered_project": filtered_project,
        },
    )


@router.post("/project-tokens/{token_id}/revoke")
async def revoke_token(request: Request, token_id: int) -> RedirectResponse:
    await ProjectToken.filter(id=token_id).update(active=False)
    return RedirectResponse("/admin/project-tokens", status_code=303)
