from collections import defaultdict, deque

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response

from ..domains import mulch_dir
from ..models import Project, RecordEdit, RecordEvent
from ..mulch import restore_record
from ..records import read_domain_records
from ._shared import is_admin, redirect_login, templates

router = APIRouter()

_ACTION_COLORS = {
    "write": "background:#d1fae5; color:#065f46",
    "edit": "background:#dbeafe; color:#1d4ed8",
    "delete": "background:#fee2e2; color:#991b1b",
}

_CONTENT_KEYS = ("content", "title", "name", "description", "resolution", "rationale")


def _record_summary(r: dict) -> str:
    for key in _CONTENT_KEYS:
        if r.get(key):
            val = str(r[key])
            return val[:140] + ("…" if len(val) > 140 else "")
    return ""


async def _load_record_map(org_slug: str, project_slug: str) -> dict[str, dict]:
    m_dir = mulch_dir(org_slug, project_slug)
    result: dict[str, dict] = {}
    expertise_dir = m_dir / "expertise"
    if expertise_dir.exists():
        for f in expertise_dir.glob("*.jsonl"):
            for r in await read_domain_records(f):
                if r.get("id"):
                    result[r["id"]] = r
    archive_dir = m_dir / "archive"
    if archive_dir.exists():
        for f in archive_dir.glob("*.jsonl"):
            for r in await read_domain_records(f):
                if r.get("id"):
                    result.setdefault(r["id"], r)
    return result


@router.get("/audit")
async def audit_page(
    request: Request,
    project: str = "",
    action: str = "",
    domain: str = "",
) -> Response:
    if not is_admin(request):
        return redirect_login()

    projects = await Project.all().prefetch_related("org").order_by("org__slug", "slug")

    events: list[dict] = []
    archived_domains: list[dict] = []
    selected_project = None

    if project and "/" in project:
        org_slug, project_slug = project.split("/", 1)
        selected_project = (
            await Project.filter(slug=project_slug, org__slug=org_slug)
            .prefetch_related("org")
            .first()
        )
        if selected_project:
            qs = RecordEvent.filter(project=selected_project)
            if action:
                qs = qs.filter(action=action)
            if domain:
                qs = qs.filter(domain__icontains=domain)
            rows = await qs.order_by("-at").limit(200).values(
                "id", "record_id", "domain", "action", "client", "at",
                "session_id", "actor__username", "actor__display_name",
            )

            # RecordEdit rows per (record_id, session_id), oldest-first.
            # Each edit event pops one entry from its queue.
            edit_rows = await RecordEdit.filter(project=selected_project).order_by("at").values(
                "record_id", "session_id", "before_snapshot"
            )
            edit_queues: dict[tuple, deque] = defaultdict(deque)
            for e in edit_rows:
                edit_queues[(e["record_id"], str(e["session_id"]))].append(e["before_snapshot"])

            # Process events oldest-first so queue pops match the right edit,
            # then reverse for newest-first display.
            record_map = await _load_record_map(org_slug, project_slug)
            edit_consumed: dict[tuple, int] = defaultdict(int)
            processed = []
            for r in reversed(rows):
                before_snap = None
                if r["action"] == "edit":
                    key = (r["record_id"], str(r["session_id"]))
                    q = edit_queues.get(key)
                    if q:
                        idx = edit_consumed[key]
                        if idx < len(q):
                            before_snap = q[idx]
                            edit_consumed[key] += 1

                rec = record_map.get(r["record_id"])
                processed.append({
                    "record_id": r["record_id"],
                    "domain": r["domain"],
                    "action": r["action"],
                    "action_color": _ACTION_COLORS.get(r["action"], "background:#f1f5f9; color:#475569"),
                    "actor": r["actor__display_name"] or r["actor__username"],
                    "at": r["at"].strftime("%Y-%m-%d %H:%M"),
                    "client": r["client"],
                    "record_type": (rec or {}).get("type", ""),
                    "record_summary": _record_summary(rec) if rec else "",
                    "before_snap": before_snap,
                })
            events = list(reversed(processed))

            archive_dir = mulch_dir(org_slug, project_slug) / "archive"
            if archive_dir.exists():
                for jsonl_file in sorted(archive_dir.glob("*.jsonl")):
                    records = await read_domain_records(jsonl_file)
                    if records:
                        archived_domains.append({"name": jsonl_file.stem, "records": records})

    return templates.TemplateResponse(
        request,
        "audit.html",
        {
            "active": "audit",
            "projects": projects,
            "selected": project,
            "selected_project": selected_project,
            "events": events,
            "archived_domains": archived_domains,
            "filter_action": action,
            "filter_domain": domain,
        },
    )


@router.post("/audit/restore")
async def restore_record_action(
    request: Request,
    project: str = Form(...),
    record_id: str = Form(...),
) -> Response:
    if not is_admin(request):
        return redirect_login()
    if "/" in project:
        org_slug, project_slug = project.split("/", 1)
        m_dir = mulch_dir(org_slug, project_slug)
        await restore_record(m_dir, record_id)
    return RedirectResponse(f"/admin/audit?project={project}", status_code=303)
