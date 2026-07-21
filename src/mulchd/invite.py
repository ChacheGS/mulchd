import secrets
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from tortoise import transactions

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
