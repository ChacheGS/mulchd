import secrets
from pathlib import Path
from typing import cast

from fastapi import APIRouter
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer
from starlette.requests import Request
from tortoise import transactions

from .config import CONNECT_COOKIE_NAME, CONNECT_COOKIE_SALT, settings
from .instance_events import log_event
from .models import InstanceEventCategory, InviteLink, InviteUse, User, UserMembership
from .oauth import get_configured_providers

router = APIRouter(prefix="/invite")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

SESSION_KEY = "pending_invite"


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
    raw = request.cookies.get(CONNECT_COOKIE_NAME, "")
    if not raw:
        return None
    try:
        return URLSafeSerializer(settings.secret_key, salt=CONNECT_COOKIE_SALT).loads(raw)
    except BadSignature:
        return None


async def validate_invite(token: str) -> InviteLink | None:
    """Steps 1-4: existence, revoked, expired, exhausted. Returns None for any failure.

    Reuses InviteLink.status (added in Task 2, src/mulchd/models/identity.py) instead of
    re-deriving revoked/expired/exhausted here, so the admin UI and this claim
    path can't drift out of sync.
    """
    invite = await InviteLink.filter(token=token).select_related("project__org").first()
    if invite is None:
        return None
    if invite.status != "active":
        return None
    return invite


async def claim_invite(invite: InviteLink, user: User) -> bool:
    """
    Atomically claim an invite for a user.
    Returns True if claimed (or already a member), False if exhausted by a concurrent claim.
    Does NOT increment use_count if user is already a member.
    """
    existing = await UserMembership.filter(user=user, project=invite.project).first()
    if existing is not None:
        return True  # already a member — silent skip, no increment

    # Tortoise's in_transaction isn't generic-parametrized in its stub.
    txn = (  # pyright: ignore[reportUnknownVariableType]
        transactions.in_transaction()  # pyright: ignore[reportUnknownMemberType]
    )
    async with txn:
        fresh = await InviteLink.select_for_update().get(id=invite.id)
        # Tortoise's IntField(null=True) stub doesn't expose Optional here.
        max_uses_reached = (
            fresh.max_uses is not None  # pyright: ignore[reportUnnecessaryComparison]
            and fresh.use_count >= fresh.max_uses
        )
        if max_uses_reached:
            return False
        fresh.use_count += 1
        await fresh.save(update_fields=["use_count"])
        await UserMembership.create(user=user, project=invite.project, role=invite.role)
        await InviteUse.create(invite=invite, user=user)
    await log_event(
        InstanceEventCategory.MEMBERSHIP_ADDED,
        actor=user,
        subject_user=user,
        project=invite.project,
        detail={"role": invite.role, "via": "invite"},
    )
    return True


@router.get("/{token}")
async def invite_landing(request: Request, token: str) -> Response:
    invite = await validate_invite(token)
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
            already_member = await UserMembership.filter(user=user, project=invite.project).exists()
            allowed_domains = cast(
                "list[str] | None",
                invite.allowed_email_domains,  # pyright: ignore[reportUnknownMemberType]  # Tortoise JSONField stub doesn't parametrize its value type
            )
            if (
                not already_member
                and allowed_domains
                and not matches_allowed_domains(user.email or "", allowed_domains)
            ):
                return templates.TemplateResponse(
                    request,
                    "invite.html",
                    {"error": "Your email is not authorized for this invite.", "invite": None},
                )
            claimed = await claim_invite(invite, user)
            if not claimed:
                return templates.TemplateResponse(
                    request,
                    "invite.html",
                    {"error": "This invite link is not valid.", "invite": None},
                )
            return RedirectResponse(
                f"/connect/projects/{invite.project.org.slug}/{invite.project.slug}",
                status_code=303,
            )

    request.session[SESSION_KEY] = token
    return templates.TemplateResponse(
        request,
        "invite.html",
        {
            "invite": invite,
            "providers": get_configured_providers(),
        },
    )
