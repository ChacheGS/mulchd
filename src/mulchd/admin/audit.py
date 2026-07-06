from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response

from ..domains import mulch_dir
from ..models import Project, RecordEvent
from ..mulch import restore_record
from ..records import read_domain_records
from ._shared import is_admin, redirect_login, templates

router = APIRouter()

_ACTION_COLORS = {
    "write": "background:#d1fae5; color:#065f46",
    "edit": "background:#dbeafe; color:#1d4ed8",
    "delete": "background:#fee2e2; color:#991b1b",
}


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
                "actor__username", "actor__display_name",
            )
            events = [
                {
                    "record_id": r["record_id"],
                    "domain": r["domain"],
                    "action": r["action"],
                    "action_color": _ACTION_COLORS.get(r["action"], "background:#f1f5f9; color:#475569"),
                    "actor": r["actor__display_name"] or r["actor__username"],
                    "at": r["at"].strftime("%Y-%m-%d %H:%M"),
                    "client": r["client"],
                }
                for r in rows
            ]

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
