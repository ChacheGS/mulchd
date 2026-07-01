from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from ..models import ProjectToken
from ._shared import is_admin, redirect_login, templates

router = APIRouter()


@router.get("/project-tokens")
async def project_tokens_page(request: Request) -> Response:
    if not is_admin(request):
        return redirect_login()
    tokens = (
        await ProjectToken.all()
        .prefetch_related("user", "project", "project__org")
        .order_by("-created_at")
    )
    return templates.TemplateResponse(
        request,
        "project_tokens.html",
        {"active": "project-tokens", "tokens": tokens},
    )


@router.post("/project-tokens/{token_id}/revoke")
async def revoke_token(request: Request, token_id: int) -> RedirectResponse:
    if not is_admin(request):
        return redirect_login()
    await ProjectToken.filter(id=token_id).update(active=False)
    return RedirectResponse("/admin/project-tokens", status_code=303)
