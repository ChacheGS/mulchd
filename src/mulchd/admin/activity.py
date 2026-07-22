from fastapi import APIRouter, Request
from fastapi.responses import Response

from ..instance_events import describe_event
from ..models import InstanceEvent, InstanceEventCategory, Project, User
from ._shared import is_admin, redirect_login, templates

router = APIRouter()

_CATEGORY_COLORS = {
    InstanceEventCategory.ADMIN_GRANTED: "background:#dbeafe; color:#1d4ed8",
    InstanceEventCategory.ADMIN_REVOKED: "background:#fee2e2; color:#991b1b",
    InstanceEventCategory.MEMBERSHIP_ADDED: "background:#d1fae5; color:#065f46",
    InstanceEventCategory.MEMBERSHIP_REMOVED: "background:#fee2e2; color:#991b1b",
    InstanceEventCategory.FIRST_LOGIN: "background:#f1f5f9; color:#475569",
    InstanceEventCategory.OAUTH_LINKED: "background:#f1f5f9; color:#475569",
    InstanceEventCategory.TOKEN_RESET: "background:#fef3c7; color:#92400e",
    InstanceEventCategory.ORG_CREATED: "background:#d1fae5; color:#065f46",
    InstanceEventCategory.PROJECT_CREATED: "background:#d1fae5; color:#065f46",
    InstanceEventCategory.USER_CREATED: "background:#d1fae5; color:#065f46",
    InstanceEventCategory.USER_DEACTIVATED: "background:#fee2e2; color:#991b1b",
    InstanceEventCategory.INVITE_CREATED: "background:#d1fae5; color:#065f46",
    InstanceEventCategory.INVITE_REVOKED: "background:#fee2e2; color:#991b1b",
}


@router.get("/activity")
async def activity_page(
    request: Request,
    category: str = "",
    actor: str = "",
    project: str = "",
) -> Response:
    if not await is_admin(request):
        return redirect_login()

    qs = InstanceEvent.all().select_related("actor", "subject_user", "project", "project__org")
    if category:
        qs = qs.filter(category=category)
    if actor:
        qs = qs.filter(actor__username=actor)
    if project and "/" in project:
        org_slug, project_slug = project.split("/", 1)
        qs = qs.filter(project__slug=project_slug, project__org__slug=org_slug)
    raw_events = await qs.order_by("-at").limit(200).all()

    rows = [
        {
            "at": e.at.strftime("%Y-%m-%d %H:%M"),
            "category": e.category,
            "category_color": _CATEGORY_COLORS.get(e.category, "background:#f1f5f9; color:#475569"),
            "description": describe_event(e),
            "actor": e.actor.display_name or e.actor.username,
        }
        for e in raw_events
    ]

    actors = await User.all().order_by("username")
    projects = await Project.all().prefetch_related("org").order_by("org__slug", "slug")

    return templates.TemplateResponse(
        request,
        "activity.html",
        {
            "active": "activity",
            "rows": rows,
            "categories": list(InstanceEventCategory),
            "actors": actors,
            "projects": projects,
            "filter_category": category,
            "filter_actor": actor,
            "filter_project": project,
        },
    )
