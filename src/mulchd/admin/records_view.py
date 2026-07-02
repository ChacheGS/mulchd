from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response

from ..domains import mulch_dir
from ..models import Project
from ..mulch import delete_record
from ..records import read_domain_records
from ._shared import is_admin, redirect_login, templates

router = APIRouter()


@router.post("/records/delete")
async def delete_record_action(
    request: Request,
    project: str = Form(...),
    domain: str = Form(...),
    record_id: str = Form(...),
) -> Response:
    if not is_admin(request):
        return redirect_login()
    if "/" in project:
        org_slug, project_slug = project.split("/", 1)
        m_dir = mulch_dir(org_slug, project_slug)
        await delete_record(m_dir, domain, record_id)
    return RedirectResponse(f"/admin/records?project={project}", status_code=303)


@router.get("/records")
async def records_page(request: Request, project: str = "") -> Response:
    if not is_admin(request):
        return redirect_login()

    projects = await Project.all().prefetch_related("org").order_by("org__slug", "slug")

    domains_data: list[dict] = []
    selected_project = None

    if project and "/" in project:
        org_slug, project_slug = project.split("/", 1)
        selected_project = (
            await Project.filter(slug=project_slug, org__slug=org_slug)
            .prefetch_related("org")
            .first()
        )
        if selected_project:
            expertise_dir = mulch_dir(org_slug, project_slug) / "expertise"
            if expertise_dir.exists():
                for jsonl_file in sorted(expertise_dir.glob("*.jsonl")):
                    records = await read_domain_records(jsonl_file)
                    if records:
                        domains_data.append(
                            {"name": jsonl_file.stem, "records": records}
                        )

    return templates.TemplateResponse(
        request,
        "records.html",
        {
            "active": "records",
            "projects": projects,
            "selected": project,
            "selected_project": selected_project,
            "domains": domains_data,
        },
    )
