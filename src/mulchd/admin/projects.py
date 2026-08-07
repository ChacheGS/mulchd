from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response

from ..instance_events import log_event
from ..models import (
    InstanceEventCategory,
    InviteLink,
    InviteUse,
    Project,
    ProjectPolicy,
    Role,
    User,
)
from ..policies import POLICIES, invalidate_policy_override, resolve_policy
from ._shared import (
    get_current_admin,
    require_admin,
    resolve_project_by_slugs,
    set_last_project_cookie,
    templates,
)

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/p/{org_slug}/{project_slug}/")
async def project_overview_page(request: Request, org_slug: str, project_slug: str) -> Response:
    project = await resolve_project_by_slugs(org_slug, project_slug)
    if project is None:
        return Response(status_code=404)
    invites = (
        await InviteLink.filter(project=project)
        .select_related("created_by")
        .order_by("-created_at")
        .all()
    )
    uses_by_invite: dict[int, list[InviteUse]] = {inv.id: [] for inv in invites}
    if invites:
        uses = (
            await InviteUse.filter(invite_id__in=[inv.id for inv in invites])
            .select_related("user")
            .order_by("used_at")
            .all()
        )
        for use in uses:
            uses_by_invite[use.invite_id].append(use)
    policies = [
        (key, definition, await resolve_policy(project, key)) for key, definition in POLICIES.items()
    ]
    response = templates.TemplateResponse(
        request,
        "project_detail.html",
        {
            # "records" just keeps the sidebar's Project group visually active while on
            # Overview — the sidebar has no dedicated "Overview" entry of its own to highlight.
            "active": "records",
            "project": project,
            "active_tab": "overview",
            "tab_path": "",
            "invites": invites,
            "uses_by_invite": uses_by_invite,
            "roles": list(Role),
            "policies": policies,
        },
    )
    set_last_project_cookie(response, org_slug, project_slug)
    return response


@router.post("/projects/{project_id}/language")
async def set_project_language(
    request: Request,
    project_id: int,
    knowledge_language: str = Form(""),
) -> Response:
    project = await Project.filter(id=project_id).select_related("org").first()
    if project is None:
        return Response(status_code=404)
    project.knowledge_language = knowledge_language.strip() or None  # type: ignore[assignment] — tortoise's CharField stub isn't null-aware
    await project.save(update_fields=["knowledge_language"])
    return RedirectResponse(f"/admin/p/{project.org.slug}/{project.slug}/", status_code=303)


@router.post("/p/{org_slug}/{project_slug}/policies/{key}")
async def set_project_policy(
    request: Request,
    org_slug: str,
    project_slug: str,
    key: str,
    value: str = Form(...),
    admin: User = Depends(get_current_admin),
) -> Response:
    project = await resolve_project_by_slugs(org_slug, project_slug)
    if project is None:
        return Response(status_code=404)
    definition = POLICIES.get(key)
    if definition is None:
        return Response(status_code=404)

    resolved = await resolve_policy(project, key)
    if resolved.source == "locked":
        return Response(status_code=400, content=f"{key} is locked by {definition.env_var}")

    try:
        # `value` is a raw form string, same shape as an env var's value —
        # `parse` (not `validate`, which expects an already-typed Python
        # value) is the callable meant to accept raw strings.
        parsed = definition.parse(value)
    except ValueError as e:
        return Response(status_code=400, content=str(e))

    await ProjectPolicy.update_or_create(  # pyright: ignore[reportUnknownMemberType] — tortoise stub doesn't fully type update_or_create
        project=project, key=key, defaults={"value": [parsed], "updated_by": admin}
    )
    # The lock-check above already populated the TTL cache (possibly with a
    # pre-write miss) — drop it now so the PRG redirect below reflects the
    # write instead of serving a stale cached value for up to the TTL window.
    invalidate_policy_override(project, key)
    await log_event(
        InstanceEventCategory.POLICY_CHANGED,
        actor=admin,
        project=project,
        detail={"key": key, "value": parsed},
    )
    return RedirectResponse(f"/admin/p/{org_slug}/{project_slug}/", status_code=303)
