import secrets
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer
from starlette.requests import Request
from tortoise import transactions

from .config import settings
from .models import InviteLink, InviteUse, User, UserMembership

router = APIRouter(prefix="/invite")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

_SESSION_KEY = "pending_invite"


def generate_invite_token() -> str:
    return secrets.token_urlsafe(32)


def matches_allowed_domains(email: str, patterns: list[str] | None) -> bool:
    """
    Returns True if the email's domain matches any pattern in the list.
    None or empty list means any email is allowed.
    Patterns: "company.com" (exact) or "*.company.com" (any subdomain, any depth).
    """
    if not patterns:
        return True
    domain = email.split("@", 1)[-1].lower()
    for pattern in patterns:
        if pattern.startswith("*."):
            suffix = pattern[2:]  # "company.com"
            if domain.endswith("." + suffix):
                return True
        else:
            if domain == pattern.lower():
                return True
    return False


def _get_invite_user_id(request: Request) -> int | None:
    """Read the connect cookie without importing from connect.py (avoids circular import)."""
    raw = request.cookies.get("mulchd_connect", "")
    if not raw:
        return None
    try:
        return URLSafeSerializer(settings.secret_key, salt="connect").loads(raw)
    except BadSignature:
        return None


async def _validate_invite(token: str) -> InviteLink | None:
    """Steps 1-4: existence, revoked, expired, exhausted. Returns None for any failure.

    Reuses InviteLink.status (added in Task 2, src/mulchd/models.py) instead of
    re-deriving revoked/expired/exhausted here, so the admin UI and this claim
    path can't drift out of sync.
    """
    invite = (
        await InviteLink.filter(token=token)
        .select_related("project__org")
        .first()
    )
    if invite is None:
        return None
    if invite.status != "active":
        return None
    return invite


async def _claim_invite(invite: InviteLink, user: User) -> bool:
    """
    Atomically claim an invite for a user.
    Returns True if claimed (or already a member), False if exhausted by a concurrent claim.
    Does NOT increment use_count if user is already a member.
    """
    existing = await UserMembership.filter(user=user, project=invite.project).first()
    if existing is not None:
        return True  # already a member — silent skip, no increment

    async with transactions.in_transaction():
        fresh = await InviteLink.select_for_update().get(id=invite.id)
        if fresh.max_uses is not None and fresh.use_count >= fresh.max_uses:
            return False
        fresh.use_count += 1
        await fresh.save(update_fields=["use_count"])
        await UserMembership.create(user=user, project=invite.project, role=invite.role)
        await InviteUse.create(invite=invite, user=user)
    return True


@router.get("/{token}")
async def invite_landing(request: Request, token: str) -> Response:
    from .oauth import get_configured_providers

    invite = await _validate_invite(token)
    if invite is None:
        return templates.TemplateResponse(
            request,
            "invite.html",
            {"error": "This invite link is not valid.", "invite": None},
        )

    user_id = _get_invite_user_id(request)
    if user_id is not None:
        user = await User.filter(id=user_id, active=True).first()
        if user is not None:
            if invite.allowed_email_domains and not matches_allowed_domains(
                user.email or "", invite.allowed_email_domains
            ):
                return templates.TemplateResponse(
                    request,
                    "invite.html",
                    {"error": "Your email is not authorized for this invite.", "invite": None},
                )
            await _claim_invite(invite, user)
            return RedirectResponse(
                f"/connect/projects/{invite.project.org.slug}/{invite.project.slug}",
                status_code=303,
            )

    request.session[_SESSION_KEY] = token
    return templates.TemplateResponse(
        request,
        "invite.html",
        {
            "invite": invite,
            "providers": get_configured_providers(),
        },
    )
