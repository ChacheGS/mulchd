from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import Response
from tortoise.functions import Count

from ..models import Organization, Project, ToolCall, User, UserMembership
from ._shared import is_admin, redirect_login, templates

router = APIRouter()

_WINDOW_DAYS = 30


@router.get("/")
async def dashboard(request: Request) -> Response:
    if not await is_admin(request):
        return redirect_login()

    since = datetime.now(timezone.utc) - timedelta(days=_WINDOW_DAYS)

    projects = await Project.all().prefetch_related("org").order_by("org__slug", "slug")

    # Aggregate tool calls per project/user/tool in one query
    rows = (
        await ToolCall.filter(called_at__gte=since)
        .annotate(count=Count("id"))
        .group_by("project_id", "author_id", "author__username", "tool")
        .values("project_id", "author_id", "author__username", "tool", "count")
    )

    # Build per-project structure
    by_project: dict[int, dict] = {}
    for p in projects:
        by_project[p.id] = {
            "project": p,
            "total": 0,
            "by_tool": defaultdict(int),
            "by_user": defaultdict(int),
        }

    for row in rows:
        pid = row["project_id"]
        if pid not in by_project:
            continue
        entry = by_project[pid]
        n = row["count"]
        entry["total"] += n
        entry["by_tool"][row["tool"]] += n
        entry["by_user"][row["author__username"] or "unknown"] += n

    project_stats = [
        {
            "project": v["project"],
            "total": v["total"],
            "by_tool": sorted(v["by_tool"].items(), key=lambda x: -x[1]),
            "by_user": sorted(v["by_user"].items(), key=lambda x: -x[1]),
        }
        for v in by_project.values()
    ]

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "active": "dashboard",
            "window_days": _WINDOW_DAYS,
            "stats": {
                "users": await User.filter(active=True).count(),
                "orgs": await Organization.all().count(),
                "projects": await Project.all().count(),
                "memberships": await UserMembership.all().count(),
            },
            "project_stats": project_stats,
        },
    )
