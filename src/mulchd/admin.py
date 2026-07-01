import hmac
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from tortoise.exceptions import IntegrityError

from .auth import create_user
from .config import settings
from .models import Organization, Project, Role, User, UserMembership

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def _is_admin(request: Request) -> bool:
    return bool(request.session.get("admin"))


def _redirect_login() -> RedirectResponse:
    return RedirectResponse("/admin/login", status_code=303)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if _is_admin(request):
        return RedirectResponse("/admin/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def login(request: Request, password: str = Form(...)):
    if hmac.compare_digest(password, settings.admin_password):
        request.session["admin"] = True
        return RedirectResponse("/admin/", status_code=303)
    return templates.TemplateResponse(
        request, "login.html", {"error": "Incorrect password"}, status_code=401
    )


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not _is_admin(request):
        return _redirect_login()
    return templates.TemplateResponse(request, "dashboard.html", {
        "active": "dashboard",
        "stats": {
            "users": await User.filter(active=True).count(),
            "orgs": await Organization.all().count(),
            "projects": await Project.all().count(),
            "memberships": await UserMembership.all().count(),
        },
    })


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, error: str = ""):
    if not _is_admin(request):
        return _redirect_login()
    users = await User.all().order_by("username")
    return templates.TemplateResponse(request, "users.html", {
        "active": "users",
        "users": users,
        "error": error,
    })


@router.post("/users")
async def create_user_route(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
):
    if not _is_admin(request):
        return _redirect_login()
    try:
        user, token = await create_user(username.strip(), display_name.strip())
    except IntegrityError:
        users = await User.all().order_by("username")
        return templates.TemplateResponse(request, "users.html", {
            "active": "users",
            "users": users,
            "error": f"Username '{username}' is already taken.",
        }, status_code=409)

    request.session["pending_token"] = {
        "username": user.username,
        "display_name": user.display_name,
        "token": token,
    }
    return RedirectResponse("/admin/users/created", status_code=303)


@router.get("/users/created", response_class=HTMLResponse)
async def user_created_page(request: Request):
    if not _is_admin(request):
        return _redirect_login()
    pending = request.session.pop("pending_token", None)
    if pending is None:
        return RedirectResponse("/admin/users", status_code=303)
    return templates.TemplateResponse(request, "user_created.html", {
        "active": "users",
        "username": pending["username"],
        "display_name": pending["display_name"],
        "token": pending["token"],
        "server_url": f"http://{settings.host}:{settings.port}",
    })


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(request: Request, user_id: int):
    if not _is_admin(request):
        return _redirect_login()
    await User.filter(id=user_id).update(active=False)
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/activate")
async def activate_user(request: Request, user_id: int):
    if not _is_admin(request):
        return _redirect_login()
    await User.filter(id=user_id).update(active=True)
    return RedirectResponse("/admin/users", status_code=303)


# ---------------------------------------------------------------------------
# Organisations
# ---------------------------------------------------------------------------

@router.get("/orgs", response_class=HTMLResponse)
async def orgs_page(request: Request, error: str = ""):
    if not _is_admin(request):
        return _redirect_login()
    orgs = await Organization.all().order_by("slug").prefetch_related("projects")
    return templates.TemplateResponse(request, "orgs.html", {
        "active": "orgs",
        "orgs": orgs,
        "error": error,
    })


@router.post("/orgs")
async def create_org(
    request: Request,
    slug: str = Form(...),
    display_name: str = Form(...),
):
    if not _is_admin(request):
        return _redirect_login()
    try:
        await Organization.create(slug=slug.strip(), display_name=display_name.strip())
    except IntegrityError:
        orgs = await Organization.all().order_by("slug").prefetch_related("projects")
        return templates.TemplateResponse(request, "orgs.html", {
            "active": "orgs",
            "orgs": orgs,
            "error": f"Org slug '{slug}' already exists.",
        }, status_code=409)
    return RedirectResponse("/admin/orgs", status_code=303)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@router.get("/projects", response_class=HTMLResponse)
async def projects_page(request: Request, error: str = ""):
    if not _is_admin(request):
        return _redirect_login()
    projects = await Project.all().order_by("slug").prefetch_related("org")
    orgs = await Organization.all().order_by("slug")
    return templates.TemplateResponse(request, "projects.html", {
        "active": "projects",
        "projects": projects,
        "orgs": orgs,
        "error": error,
    })


@router.post("/projects")
async def create_project(
    request: Request,
    org_id: int = Form(...),
    slug: str = Form(...),
    display_name: str = Form(...),
):
    if not _is_admin(request):
        return _redirect_login()
    org = await Organization.get_or_none(id=org_id)
    if org is None:
        return RedirectResponse("/admin/projects", status_code=303)
    try:
        await Project.create(slug=slug.strip(), display_name=display_name.strip(), org=org)
    except IntegrityError:
        projects = await Project.all().order_by("slug").prefetch_related("org")
        orgs = await Organization.all().order_by("slug")
        return templates.TemplateResponse(request, "projects.html", {
            "active": "projects",
            "projects": projects,
            "orgs": orgs,
            "error": f"Project slug '{slug}' already exists in that org.",
        }, status_code=409)
    return RedirectResponse("/admin/projects", status_code=303)


# ---------------------------------------------------------------------------
# Memberships
# ---------------------------------------------------------------------------

@router.get("/memberships", response_class=HTMLResponse)
async def memberships_page(request: Request, user: str = "", error: str = ""):
    if not _is_admin(request):
        return _redirect_login()
    memberships = await UserMembership.all().prefetch_related("user", "project", "project__org")
    users = await User.filter(active=True).order_by("username")
    projects = await Project.all().order_by("slug").prefetch_related("org")
    return templates.TemplateResponse(request, "memberships.html", {
        "active": "memberships",
        "memberships": memberships,
        "users": users,
        "projects": projects,
        "roles": list(Role),
        "preselect_user": user,
        "error": error,
    })


@router.post("/memberships")
async def add_membership(
    request: Request,
    user_id: int = Form(...),
    project_id: int = Form(...),
    role: str = Form(...),
):
    if not _is_admin(request):
        return _redirect_login()
    user = await User.get_or_none(id=user_id)
    project = await Project.get_or_none(id=project_id)
    if user is None or project is None:
        return RedirectResponse("/admin/memberships", status_code=303)
    try:
        await UserMembership.create(user=user, project=project, role=Role(role))
    except IntegrityError:
        memberships = await UserMembership.all().prefetch_related("user", "project", "project__org")
        users = await User.filter(active=True).order_by("username")
        projects = await Project.all().order_by("slug").prefetch_related("org")
        return templates.TemplateResponse(request, "memberships.html", {
            "active": "memberships",
            "memberships": memberships,
            "users": users,
            "projects": projects,
            "roles": list(Role),
            "preselect_user": "",
            "error": f"{user.username} already has access to that project.",
        }, status_code=409)
    return RedirectResponse("/admin/memberships", status_code=303)


@router.post("/memberships/{membership_id}/remove")
async def remove_membership(request: Request, membership_id: int):
    if not _is_admin(request):
        return _redirect_login()
    await UserMembership.filter(id=membership_id).delete()
    return RedirectResponse("/admin/memberships", status_code=303)
