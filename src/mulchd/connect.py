from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

from authlib.integrations.base_client import OAuthError
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer

from mcp.server.auth.provider import construct_redirect_uri

from .admin_grants import maybe_bootstrap_admin
from .auth import (
    authenticate_global_token,
    create_project_token,
    create_user_from_oauth,
    generate_token,
)
from .config import CONNECT_COOKIE_NAME, CONNECT_COOKIE_SALT, settings
from .instance_events import (
    log_event,  # pyright: ignore[reportUnknownVariableType]  # instance_events.py's bare `dict` detail param is fixed in a later strict-mode task
)
from .invite import SESSION_KEY as _INVITE_SESSION_KEY
from .invite import (
    claim_invite,
    matches_allowed_domains,
    validate_invite,
)
from .mcp_auth import AUTH_CODE_TTL, hash_token
from .models import (
    InstanceEventCategory,
    OAuthClient,
    OAuthCode,
    OAuthGrant,
    OAuthIdentity,
    Organization,
    Project,
    ProjectToken,
    Role,
    User,
    UserMembership,
    min_role,
    roles_up_to,
)
from .oauth import get_configured_providers, oauth

router = APIRouter(prefix="/connect")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

_CONNECT_COOKIE = CONNECT_COOKIE_NAME
_REMEMBER_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _signer() -> URLSafeSerializer:
    return URLSafeSerializer(settings.secret_key, salt=CONNECT_COOKIE_SALT)


def _slug_to_env(s: str) -> str:
    return s.upper().replace("-", "_")


def build_connect_snippets(base_url: str, org: str, project: str, token: str) -> dict[str, str]:
    env_var = f"MULCHD_TOKEN_{_slug_to_env(org)}_{_slug_to_env(project)}"
    mcp_json = (
        "{\n"
        '  "mcpServers": {\n'
        '    "mulchd": {\n'
        '      "type": "http",\n'
        f'      "url": "{base_url}/mcp",\n'
        f'      "headers": {{ "Authorization": "Bearer ${{{env_var}}}" }}\n'
        "    }\n"
        "  }\n"
        "}"
    )
    settings_local = (
        "{\n"
        '  "enabledMcpServersJson": ["mulchd"],\n'
        '  "env": {\n'
        f'    "{env_var}": "{token}"\n'
        "  }\n"
        "}"
    )
    desktop = (
        "{\n"
        '  "mcpServers": {\n'
        f'    "mulchd-{org}-{project}": {{\n'
        '      "command": "npx",\n'
        f'      "args": ["-y", "mcp-remote@latest", "{base_url}/mcp",\n'
        f'               "--header", "Authorization:${{{env_var}}}"],\n'
        f'      "env": {{ "{env_var}": "Bearer {token}" }}\n'
        "    }}\n"
        "  }\n"
        "}"
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
        secure=settings.is_https,
        max_age=max_age,
    )


def get_connect_user_id(request: Request) -> int | None:
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
    user_id = get_connect_user_id(request)
    if user_id is None:
        return None
    return await User.filter(id=user_id, active=True).first()


async def _require_membership(
    user: User, org_slug: str, project_slug: str
) -> tuple[Organization, Project]:
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


async def _resolve_oauth_identity(provider: str, sub: str, email: str | None) -> User | None:
    """
    Resolve a provider identity to a local User.
    Returns None for unknown identity, email mismatch, and inactive users —
    callers show the same generic error for all three.
    """
    identity = await OAuthIdentity.filter(provider=provider, sub=sub).select_related("user").first()
    if identity is not None:
        return identity.user if identity.user.active else None

    if not email:
        return None
    user = await User.filter(email=email, active=True).first()
    if user is None:
        return None
    await OAuthIdentity.create(user=user, provider=provider, sub=sub)
    await log_event(
        InstanceEventCategory.OAUTH_LINKED,
        actor=user,
        subject_user=user,
        detail={"provider": provider},
    )
    return user


async def _maybe_log_first_login(user: User, provider: str) -> None:
    """
    If user has never logged in before, record it. No-ops for accounts that
    already have first_login_at set — including brand-new OAuth-created
    accounts, which set it directly in create_user_from_oauth (this call is
    then a harmless no-op for them, not a duplicate log entry).
    """
    if (
        user.first_login_at is not None
    ):  # pyright: ignore[reportUnnecessaryComparison]  # Tortoise's DatetimeField(null=True) stub doesn't expose Optional here
        return
    user.first_login_at = datetime.now(UTC)
    await user.save(update_fields=["first_login_at"])
    await log_event(
        InstanceEventCategory.FIRST_LOGIN,
        actor=user,
        subject_user=user,
        detail={"provider": provider},
    )


def _safe_return_to(value: str | None) -> str | None:
    """Only ever redirect to a same-origin /connect/* path — never an absolute URL."""
    if value and value.startswith("/connect/") and "://" not in value:
        return value
    return None


async def _claim_pending_invite(request: Request, user: User) -> str | None:
    """
    Claim the session's pending invite for user, if one is stashed.
    Returns None if there was no pending invite. Otherwise returns one of:
    "claimed", "invalid" (invite no longer valid or claim lost a concurrency race),
    "domain_denied" (email doesn't match the invite's allowed domains).
    """
    pending_invite_token = request.session.pop(_INVITE_SESSION_KEY, None)
    if not pending_invite_token:
        return None
    invite = await validate_invite(pending_invite_token)
    if invite is None:
        return "invalid"
    domains_ok = matches_allowed_domains(
        user.email or "", invite.allowed_email_domains
    )  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]  # Tortoise's JSONField stub doesn't expose the list[str] this field actually stores
    if (
        invite.allowed_email_domains and not domains_ok
    ):  # pyright: ignore[reportUnknownMemberType]  # Tortoise's JSONField stub doesn't expose the list[str] this field actually stores
        return "domain_denied"
    claimed = await claim_invite(invite, user)
    return "claimed" if claimed else "invalid"


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
async def connect_login_page(request: Request, return_to: str | None = None):
    safe_return_to = _safe_return_to(return_to)
    if safe_return_to is not None:
        request.session["return_to"] = safe_return_to
    if await _require_user(request) is not None:
        return RedirectResponse(
            request.session.pop("return_to", "/connect/projects"), status_code=303
        )
    return templates.TemplateResponse(
        request, "connect/entry.html", {"providers": get_configured_providers()}
    )


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
            {"error": "Invalid token.", "providers": get_configured_providers()},
            status_code=401,
        )

    await _maybe_log_first_login(user, "token")

    remember = remember_me == "on"

    redirect_url = request.session.pop("return_to", "/connect/projects")
    invite_outcome = await _claim_pending_invite(request, user)
    if invite_outcome in ("invalid", "domain_denied"):
        redirect_url = f"/connect/projects?invite_error={invite_outcome}"

    if request.headers.get("HX-Request"):
        response = Response(status_code=200)
        response.headers["HX-Redirect"] = redirect_url
        _set_connect_cookie(response, user.id, remember)
        return response

    response = RedirectResponse(redirect_url, status_code=303)
    _set_connect_cookie(response, user.id, remember)
    return response


_INVITE_ERROR_MESSAGES = {
    "invalid": "Your invite link is no longer valid (it may have been revoked, expired, or already used up), so the membership it would have granted wasn't added.",
    "domain_denied": "Your account's email isn't authorized for that invite link's allowed domains, so the membership it would have granted wasn't added.",
}


@router.get("/projects", response_class=HTMLResponse)
async def connect_projects(request: Request, invite_error: str | None = None):
    user = await _require_user(request)
    if user is None:
        return RedirectResponse("/connect", status_code=303)

    memberships = await UserMembership.filter(user=user).select_related("project__org").all()
    grants = await OAuthGrant.filter(user=user).select_related("client", "project__org").all()
    return templates.TemplateResponse(
        request,
        "connect/projects.html",
        {
            "user": user,
            "memberships": memberships,
            "grants": grants,
            # Only a known outcome gets a message — never reflect an arbitrary
            # query value back into the page.
            "invite_error": _INVITE_ERROR_MESSAGES.get(invite_error or ""),
        },
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
    snippets = build_connect_snippets(
        settings.resolved_base_url, org.slug, project.slug, token_value
    )
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


@router.get("/auth/{provider}/start")
async def oauth_start(request: Request, provider: str) -> Response:
    configured = {p.key for p in get_configured_providers()}
    if provider not in configured:
        raise HTTPException(status_code=404)
    redirect_uri = f"{settings.resolved_base_url}/connect/auth/{provider}/callback"
    client = cast(
        Any, oauth.create_client(provider)
    )  # pyright: ignore[reportUnknownMemberType]  # authlib's OAuth client registry isn't typed
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/auth/{provider}/callback")
async def oauth_callback(request: Request, provider: str):
    configured = {p.key for p in get_configured_providers()}
    if provider not in configured:
        raise HTTPException(status_code=404)

    try:
        auth_client = cast(
            Any, oauth.create_client(provider)
        )  # pyright: ignore[reportUnknownMemberType]  # authlib's OAuth client registry isn't typed
        token = await auth_client.authorize_access_token(request)
    except OAuthError:
        return templates.TemplateResponse(
            request,
            "connect/entry.html",
            {
                "error": "Authentication failed. Please try again.",
                "providers": get_configured_providers(),
            },
            status_code=400,
        )

    # Extract sub and email per provider
    if provider == "github":
        client = cast(
            Any, oauth.create_client("github")
        )  # pyright: ignore[reportUnknownMemberType]  # authlib's OAuth client registry isn't typed
        user_resp = await client.get("https://api.github.com/user", token=token)
        if user_resp.status_code != 200:
            return templates.TemplateResponse(
                request,
                "connect/entry.html",
                {
                    "error": "Could not fetch GitHub profile. Please try again.",
                    "providers": get_configured_providers(),
                },
                status_code=400,
            )
        sub = str(user_resp.json().get("id", ""))
        emails_resp = await client.get("https://api.github.com/user/emails", token=token)
        if emails_resp.status_code != 200:
            return templates.TemplateResponse(
                request,
                "connect/entry.html",
                {
                    "error": "Could not fetch GitHub email addresses. Please try again.",
                    "providers": get_configured_providers(),
                },
                status_code=400,
            )
        emails = emails_resp.json()
        email = next(
            (e["email"] for e in emails if e.get("primary") and e.get("verified")),
            None,
        )
        username = user_resp.json().get("login", "")
        display_name = user_resp.json().get("name") or username
    else:  # any non-github OIDC provider — all speak standard userinfo claims
        userinfo = token.get("userinfo", {})
        sub = userinfo.get("sub", "")
        email = userinfo.get("email")
        username = userinfo.get("preferred_username") or (email or "").split("@")[0]
        display_name = userinfo.get("name") or username

    if not sub or not email:
        return templates.TemplateResponse(
            request,
            "connect/entry.html",
            {
                "error": "Provider did not return a verified email address.",
                "providers": get_configured_providers(),
            },
            status_code=400,
        )

    pending_invite_token = request.session.get(_INVITE_SESSION_KEY)
    user = await _resolve_oauth_identity(provider, sub, email)

    if user is None:
        if pending_invite_token:
            # New user arriving via invite — create account from OAuth data
            invite = await validate_invite(pending_invite_token)
            if invite is None:
                request.session.pop(_INVITE_SESSION_KEY, None)
                return templates.TemplateResponse(
                    request,
                    "connect/entry.html",
                    {
                        "error": "The invite link is no longer valid.",
                        "providers": get_configured_providers(),
                    },
                    status_code=403,
                )
            domains_ok = matches_allowed_domains(
                email or "", invite.allowed_email_domains
            )  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]  # Tortoise's JSONField stub doesn't expose the list[str] this field actually stores
            if (
                invite.allowed_email_domains and not domains_ok
            ):  # pyright: ignore[reportUnknownMemberType]  # Tortoise's JSONField stub doesn't expose the list[str] this field actually stores
                request.session.pop(_INVITE_SESSION_KEY, None)
                return templates.TemplateResponse(
                    request,
                    "connect/entry.html",
                    {
                        "error": "Your email is not authorized for this invite.",
                        "providers": get_configured_providers(),
                    },
                    status_code=403,
                )
            # username/display_name derived from provider profile data above
            user = await create_user_from_oauth(provider, sub, email, username, display_name)
        else:
            return templates.TemplateResponse(
                request,
                "connect/entry.html",
                {
                    "error": "No account found for this identity. Ask an admin to create one.",
                    "providers": get_configured_providers(),
                },
                status_code=403,
            )

    await maybe_bootstrap_admin(user)
    await _maybe_log_first_login(user, provider)

    # Claim pending invite if present (covers both new and existing users)
    redirect_url = request.session.pop("return_to", "/connect/projects")
    invite_outcome = await _claim_pending_invite(request, user)
    if invite_outcome in ("invalid", "domain_denied"):
        redirect_url = f"/connect/projects?invite_error={invite_outcome}"

    response = RedirectResponse(redirect_url, status_code=303)
    _set_connect_cookie(response, user.id, remember=False)
    return response


def _redirect_uri_registered(oauth_client: OAuthClient, redirect_uri: str) -> bool:
    """
    The mcp SDK's own /authorize handler validates redirect_uri against the client's
    registered redirect_uris before ever calling MulchdOAuthProvider.authorize() — but
    /connect/oauth-consent is a separately-reachable HTTP endpoint. Without this check,
    a crafted link with a legitimate client_id but an attacker-controlled redirect_uri
    would let a logged-in user's "Allow" click hand the authorization code to that
    attacker instead of the real client.
    """
    return redirect_uri in (
        oauth_client.client_metadata.get("redirect_uris") or []
    )  # pyright: ignore[reportUnknownMemberType]  # Tortoise's JSONField stub doesn't expose the dict shape this field actually stores


async def _issue_oauth_code(
    grant: OAuthGrant,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    scope: str,
    state: str = "",
) -> RedirectResponse:
    # client_id must be OAuthClient.client_id (the SDK-facing string business key),
    # not grant.client_id — Tortoise's raw FK attribute on grant.client is the related
    # OAuthClient row's integer primary key, not its client_id string. Passing the
    # caller's already-loaded OAuthClient row's .client_id avoids that trap.
    code = generate_token()
    await OAuthCode.create(
        code_hash=hash_token(code),
        client_id=client_id,
        grant=grant,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        scope=scope or None,
        expires_at=datetime.now(UTC) + AUTH_CODE_TTL,
    )
    return RedirectResponse(
        construct_redirect_uri(redirect_uri, code=code, state=state or None),
        status_code=302,
    )


@router.get("/oauth-consent", response_class=HTMLResponse)
async def oauth_consent_page(
    request: Request,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    state: str = "",
    scope: str = "",
):
    user = await _require_user(request)
    if user is None:
        return_to = f"/connect/oauth-consent?{request.url.query}"
        return RedirectResponse(f"/connect?return_to={quote(return_to)}", status_code=303)

    oauth_client = await OAuthClient.filter(client_id=client_id).first()
    if oauth_client is None:
        return Response(status_code=404)
    if not _redirect_uri_registered(oauth_client, redirect_uri):
        return Response(status_code=400)

    existing_grant = (
        await OAuthGrant.filter(client=oauth_client, user=user).select_related("project").first()
    )
    if existing_grant is not None:
        return await _issue_oauth_code(
            existing_grant, oauth_client.client_id, redirect_uri, code_challenge, scope, state
        )

    memberships = await UserMembership.filter(user=user).select_related("project__org").all()
    return templates.TemplateResponse(
        request,
        "connect/oauth_consent.html",
        {
            "user": user,
            "client_name": oauth_client.client_metadata.get("client_name")
            or client_id,  # pyright: ignore[reportUnknownMemberType]  # Tortoise's JSONField stub doesn't expose the dict shape this field actually stores
            "memberships": memberships,
            "role_options": {m.project.id: roles_up_to(m.role) for m in memberships},
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "state": state,
            "scope": scope,
        },
    )


@router.post("/oauth-consent")
async def oauth_consent_submit(
    request: Request,
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    code_challenge: str = Form(...),
    state: str = Form(default=""),
    scope: str = Form(default=""),
    project_id: int = Form(default=0),
    decision: str = Form(...),
):
    user = await _require_user(request)
    if user is None:
        return RedirectResponse("/connect", status_code=303)

    oauth_client = await OAuthClient.filter(client_id=client_id).first()
    if oauth_client is None:
        return Response(status_code=404)
    if not _redirect_uri_registered(oauth_client, redirect_uri):
        return Response(status_code=400)

    if decision != "allow":
        return RedirectResponse(
            construct_redirect_uri(redirect_uri, error="access_denied", state=state or None),
            status_code=302,
        )

    project = await Project.filter(id=project_id).first()
    membership = (
        await UserMembership.filter(user=user, project=project).first() if project else None
    )
    if project is None or membership is None:
        return Response(status_code=403)

    form = await request.form()
    raw_role = form.get(f"role_{project_id}")
    requested_role = membership.role
    if isinstance(raw_role, str):
        try:
            requested_role = Role(raw_role)
        except ValueError:
            # Intentionally silent, unlike admin/memberships.py and admin/invites.py's
            # unguarded Role(role) (which 500s on bad input): this form is submitted by
            # an untrusted, user-tamperable client, so falling back to the membership
            # role is the correct behavior here, not a gap to align with the admin forms.
            pass
    granted_role = min_role(membership.role, requested_role)

    grant = await OAuthGrant.filter(client=oauth_client, user=user).first()
    if grant is None:
        grant = await OAuthGrant.create(
            client=oauth_client, user=user, project=project, granted_role=granted_role
        )
    elif grant.project_id != project.id:
        # Re-consenting for a different project only; if project_id is unchanged, an
        # updated role selection is NOT persisted here. This mirrors the pre-existing
        # project-reassignment gate and is an accepted, documented gap (see plan's
        # "Deferred / explicitly out of scope"), not something to couple/decouple later.
        grant.project = project
        grant.granted_role = granted_role
        await grant.save()

    return await _issue_oauth_code(
        grant, oauth_client.client_id, redirect_uri, code_challenge, scope, state
    )


@router.post("/apps/{grant_id}/revoke")
async def connect_apps_revoke(request: Request, grant_id: int):
    user = await _require_user(request)
    if user is None:
        return RedirectResponse("/connect", status_code=303)

    grant = await OAuthGrant.filter(id=grant_id, user=user).first()
    if grant is None:
        return Response(status_code=404)

    await grant.delete()
    return RedirectResponse("/connect/projects", status_code=303)


@router.get("/logout")
async def connect_logout():
    response = RedirectResponse("/connect", status_code=303)
    response.delete_cookie(_CONNECT_COOKIE)
    return response
