from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer

from .auth import authenticate_global_token, create_project_token
from .config import settings
from .models import Organization, Project, ProjectToken, User, UserMembership

router = APIRouter(prefix="/connect")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

_CONNECT_COOKIE = "mulchd_connect"
_REMEMBER_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _signer() -> URLSafeSerializer:
    return URLSafeSerializer(settings.secret_key, salt="connect")


def _slug_to_env(s: str) -> str:
    return s.upper().replace("-", "_")


def build_connect_snippets(base_url: str, org: str, project: str, token: str) -> dict:
    env_var = f"MULCHD_TOKEN_{_slug_to_env(org)}_{_slug_to_env(project)}"
    mcp_json = (
        '{\n'
        '  "mcpServers": {\n'
        '    "mulchd": {\n'
        '      "type": "http",\n'
        f'      "url": "{base_url}/mcp",\n'
        f'      "headers": {{ "Authorization": "Bearer ${{{env_var}}}" }}\n'
        '    }\n'
        '  }\n'
        '}'
    )
    settings_local = (
        '{\n'
        '  "enabledMcpServersJson": ["mulchd"],\n'
        '  "env": {\n'
        f'    "{env_var}": "{token}"\n'
        '  }\n'
        '}'
    )
    desktop = (
        '{\n'
        '  "mcpServers": {\n'
        f'    "mulchd-{org}-{project}": {{\n'
        '      "command": "npx",\n'
        f'      "args": ["-y", "mcp-remote@latest", "{base_url}/mcp",\n'
        f'               "--header", "Authorization:${{{env_var}}}"],\n'
        f'      "env": {{ "{env_var}": "Bearer {token}" }}\n'
        '    }}\n'
        '  }\n'
        '}'
    )
    return {"mcp_json": mcp_json, "settings_local": settings_local, "desktop": desktop}


# ── Cookie auth helpers ───────────────────────────────────────────────────────

def _set_connect_cookie(response: Response, user_id: int, remember: bool) -> None:
    signed = _signer().dumps(user_id)
    max_age = _REMEMBER_MAX_AGE if remember else None
    response.set_cookie(
        _CONNECT_COOKIE,
        signed,
        httponly=True,
        samesite="lax",
        max_age=max_age,
    )


def _get_connect_user_id(request: Request) -> int | None:
    raw = request.cookies.get(_CONNECT_COOKIE, "")
    if not raw:
        return None
    try:
        return _signer().loads(raw)
    except BadSignature:
        return None


# ── Auth requirement helpers ──────────────────────────────────────────────────

async def _require_user(request: Request) -> User | None:
    """
    Extract and validate the user from the connect cookie.
    Returns User if valid and active, None otherwise.
    """
    user_id = _get_connect_user_id(request)
    if user_id is None:
        return None
    return await User.filter(id=user_id, active=True).first()


async def _require_membership(user: User, org_slug: str, project_slug: str) -> tuple[Organization, Project]:
    """
    Validate user membership to org/project.
    Returns (org, project) or raises HTTPException(404) if invalid.
    """
    org = await Organization.filter(slug=org_slug).first()
    if org is None:
        raise HTTPException(status_code=404)
    project = await Project.filter(slug=project_slug, org=org).select_related("org").first()
    if project is None:
        raise HTTPException(status_code=404)
    if not await UserMembership.filter(user=user, project=project).exists():
        raise HTTPException(status_code=404)
    return org, project


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def connect_login_page(request: Request):
    user_id = _get_connect_user_id(request)
    if user_id is not None:
        user = await User.filter(id=user_id, active=True).first()
        if user is not None:
            return RedirectResponse("/connect/projects", status_code=303)
    return templates.TemplateResponse(request, "connect/entry.html", {})


@router.post("", response_class=HTMLResponse)
async def connect_login(
    request: Request,
    token: str = Form(...),
    remember_me: str = Form(default=""),
):
    user = await authenticate_global_token(token)
    if user is None:
        return templates.TemplateResponse(
            request,
            "connect/entry.html",
            {"error": "Invalid token."},
            status_code=401,
        )

    remember = remember_me == "on"

    if request.headers.get("HX-Request"):
        response = Response(status_code=200)
        response.headers["HX-Redirect"] = "/connect/projects"
        _set_connect_cookie(response, user.id, remember)
        return response

    response = RedirectResponse("/connect/projects", status_code=303)
    _set_connect_cookie(response, user.id, remember)
    return response


@router.get("/projects", response_class=HTMLResponse)
async def connect_projects(request: Request):
    user = await _require_user(request)
    if user is None:
        return RedirectResponse("/connect", status_code=303)

    memberships = await UserMembership.filter(user=user).select_related("project__org").all()
    return templates.TemplateResponse(
        request,
        "connect/projects.html",
        {"user": user, "memberships": memberships},
    )


@router.get("/projects/{org_slug}/{project_slug}", response_class=HTMLResponse)
async def connect_project_page(request: Request, org_slug: str, project_slug: str):
    user = await _require_user(request)
    if user is None:
        return RedirectResponse("/connect", status_code=303)

    org, project = await _require_membership(user, org_slug, project_slug)

    tokens = await ProjectToken.filter(user=user, project=project, active=True).all()
    return templates.TemplateResponse(
        request,
        "connect/project.html",
        {"user": user, "org": org, "project": project, "tokens": tokens},
    )


@router.post("/projects/{org_slug}/{project_slug}/mint", response_class=HTMLResponse)
async def connect_mint_token(
    request: Request,
    org_slug: str,
    project_slug: str,
    label: str = Form(default=""),
):
    user = await _require_user(request)
    if user is None:
        return RedirectResponse("/connect", status_code=303)

    org, project = await _require_membership(user, org_slug, project_slug)

    _, token_value = await create_project_token(user, project, label)
    snippets = build_connect_snippets(settings.resolved_base_url, org.slug, project.slug, token_value)
    tokens = await ProjectToken.filter(user=user, project=project, active=True).all()
    return templates.TemplateResponse(
        request,
        "connect/partials/snippet_tabs.html",
        {"snippets": snippets, "org": org, "project": project, "tokens": tokens},
    )


@router.post("/projects/{org_slug}/{project_slug}/revoke/{token_id}", response_class=HTMLResponse)
async def connect_revoke_token(
    request: Request,
    org_slug: str,
    project_slug: str,
    token_id: int,
):
    user = await _require_user(request)
    if user is None:
        return RedirectResponse("/connect", status_code=303)

    org, project = await _require_membership(user, org_slug, project_slug)

    pt = await ProjectToken.filter(id=token_id, user=user, project=project, active=True).first()
    if pt is None:
        return Response(status_code=404)

    pt.active = False
    await pt.save()

    tokens = await ProjectToken.filter(user=user, project=project, active=True).all()
    return templates.TemplateResponse(
        request,
        "connect/partials/token_list.html",
        {"org": org, "project": project, "tokens": tokens},
    )


@router.get("/logout")
async def connect_logout():
    response = RedirectResponse("/connect", status_code=303)
    response.delete_cookie(_CONNECT_COOKIE)
    return response
