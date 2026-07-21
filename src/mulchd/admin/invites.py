from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response

from ..invite import generate_invite_token
from ..models import InviteLink, Project, Role
from ._shared import is_admin, redirect_login

router = APIRouter()


@router.post("/projects/{project_id}/invites")
async def create_invite(
    request: Request,
    project_id: int,
    role: str = Form("writer"),
    max_uses: str = Form(""),
    expires_in: str = Form(""),
    allowed_email_domains: str = Form(""),
) -> Response:
    if not is_admin(request):
        return redirect_login()
    project = await Project.get_or_none(id=project_id)
    if project is None:
        return Response(status_code=404)

    expires_at = None
    if expires_in.strip():
        expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=int(expires_in))

    parsed_max_uses = int(max_uses.strip()) if max_uses.strip() else None

    domain_lines = [d.strip() for d in allowed_email_domains.splitlines() if d.strip()]
    domains = domain_lines if domain_lines else None

    token = generate_invite_token()
    await InviteLink.create(
        token=token,
        project=project,
        role=Role(role),
        max_uses=parsed_max_uses,
        expires_at=expires_at,
        allowed_email_domains=domains,
    )
    return RedirectResponse(f"/admin/projects/{project_id}?new_token={token}", status_code=303)


@router.post("/invites/{invite_id}/revoke")
async def revoke_invite(request: Request, invite_id: int) -> Response:
    if not is_admin(request):
        return redirect_login()
    invite = await InviteLink.get_or_none(id=invite_id)
    if invite is None:
        return Response(status_code=404)
    invite.revoked = True
    await invite.save(update_fields=["revoked"])
    project_id = invite.project_id
    return RedirectResponse(f"/admin/projects/{project_id}", status_code=303)
