from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from tortoise import connections
from tortoise.functions import Count

from ..models import Project, ToolCall
from ._shared import is_admin

router = APIRouter()

_PERIODS = {
    "day": ("day", 30, "%Y-%m-%d"),
    "week": ("week", 84, "%Y-%m-%d"),
    "month": ("month", 365, "%Y-%m"),
}


@router.get("/api/usage/{org}/{project}")
async def usage_data(request: Request, org: str, project: str, period: str = "week"):
    if not await is_admin(request):
        raise HTTPException(status_code=403)
    if period not in _PERIODS:
        raise HTTPException(status_code=400, detail="period must be day, week, or month")

    trunc, lookback_days, fmt = _PERIODS[period]

    proj = await Project.filter(slug=project, org__slug=org).first()
    if proj is None:
        raise HTTPException(status_code=404)

    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    # date_trunc has no ORM equivalent — raw SQL only for the chart buckets
    conn = connections.get("default")
    chart_rows = await conn.execute_query_dict(
        f"""
        SELECT date_trunc('{trunc}', called_at AT TIME ZONE 'UTC') AS bucket,
               count(*)::int AS n
        FROM tool_calls
        WHERE project_id = $1 AND called_at >= $2
        GROUP BY bucket ORDER BY bucket
        """,
        [proj.id, since],
    )

    by_tool = (
        await ToolCall.filter(project=proj, called_at__gte=since)
        .annotate(n=Count("id"))
        .group_by("tool")
        .order_by("-n")
        .values("tool", "n")
    )

    by_user = (
        await ToolCall.filter(project=proj, called_at__gte=since)
        .annotate(n=Count("id"))
        .group_by("author__username")
        .order_by("-n")
        .values("author__username", "n")
    )

    return JSONResponse(
        {
            "labels": [r["bucket"].strftime(fmt) for r in chart_rows],
            "counts": [r["n"] for r in chart_rows],
            "by_tool": [[r["tool"], r["n"]] for r in by_tool],
            "by_user": [[r["author__username"], r["n"]] for r in by_user],
        }
    )
