import re
from importlib.metadata import version as _pkg_version
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from ..admin_grants import is_superadmin
from ..connect import get_connect_user_id
from ..models import Project, User

# Matches the pattern already declared (but never enforced server-side) on the
# org/project creation forms' `pattern="[a-z0-9\-]+"` attribute. Org and project
# slugs are joined with "/" throughout the admin UI (the admin_last_project
# cookie, ?project=org/slug query params, /admin/p/{org_slug}/{project_slug}/...
# routes) — a slug containing "/" would make that join ambiguous to parse back
# apart, and one containing other URL-reserved characters could produce a
# malformed or unexpected navigation target.
_SLUG_RE = re.compile(r"^[a-z0-9-]+$")


def is_valid_slug(slug: str) -> bool:
    return bool(_SLUG_RE.match(slug))


# Templates live at src/mulchd/templates/, one level above this package.
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
templates.env.globals["mulchd_version"] = _pkg_version(
    "mulchd"
)  # pyright: ignore[reportArgumentType]  # jinja2's Environment.globals stub types values as its own builtin-global set, not arbitrary str


async def get_admin_user(request: Request) -> User | None:
    """Resolve the authenticated User for this request, if they hold an active SUPERADMIN grant."""
    user_id = get_connect_user_id(request)
    if user_id is None:
        return None
    user = await User.filter(id=user_id, active=True).first()
    if user is None:
        return None
    if not await is_superadmin(user):
        return None
    return user


async def is_admin(request: Request) -> bool:
    return await get_admin_user(request) is not None


class AdminRequired(Exception):
    """Raised by require_admin/get_current_admin when the caller isn't an
    active superadmin. Caught by the app-level exception handler in main.py,
    which redirects to /connect — this is what lets a router-level FastAPI
    dependency reject a request the same way an inline route check used to."""


async def require_admin(request: Request) -> None:
    if not await is_admin(request):
        raise AdminRequired()


async def get_current_admin(request: Request) -> User:
    admin = await get_admin_user(request)
    if admin is None:
        raise AdminRequired()
    return admin


async def require_admin_json(request: Request) -> None:
    if not await is_admin(request):
        raise HTTPException(status_code=403)


def redirect_login() -> RedirectResponse:
    return RedirectResponse("/connect", status_code=303)


def parse_project_ref(project: str) -> tuple[str, str] | None:
    """Split an "org-slug/project-slug" query param, or None if malformed/empty."""
    if not project or "/" not in project:
        return None
    org_slug, project_slug = project.split("/", 1)
    return org_slug, project_slug


async def resolve_project(project: str) -> Project | None:
    """Parse and look up an "org-slug/project-slug" query param in one call."""
    ref = parse_project_ref(project)
    if ref is None:
        return None
    org_slug, project_slug = ref
    return await resolve_project_by_slugs(org_slug, project_slug)


ADMIN_LAST_PROJECT_COOKIE = "admin_last_project"


async def resolve_project_by_slugs(org_slug: str, project_slug: str) -> Project | None:
    """Resolve a project from URL path slugs, with org prefetched so templates
    can read project.org.slug without an extra query. Mirrors resolve_project's
    prefetch pattern for a query-param-style "org/project" string."""
    return (
        await Project.filter(slug=project_slug, org__slug=org_slug).prefetch_related("org").first()
    )


def set_last_project_cookie(response: Response, org_slug: str, project_slug: str) -> None:
    """Remember the last project visited via a project-scoped admin page, purely
    as a sidebar-navigation convenience — never a source of truth for access
    control or page behavior. If this cookie is missing, stale, or tampered
    with, the worst case is the sidebar's Knowledge links fall back to the
    Projects list instead of jumping straight to a project; nothing more."""
    response.set_cookie(
        ADMIN_LAST_PROJECT_COOKIE,
        f"{org_slug}/{project_slug}",
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 365,
    )
