import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from ..domains import mulch_dir
from ..models import Project
from ..mulch import delete_record, edit_record
from ..records import read_domain_records
from ._shared import (
    parse_project_ref,
    require_admin,
    resolve_project_by_slugs,
    set_last_project_cookie,
    templates,
)

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/records/count")
async def records_count(request: Request, project: str = "") -> Response:
    count = 0
    ref = parse_project_ref(project)
    if ref:
        org_slug, project_slug = ref
        expertise_dir = mulch_dir(org_slug, project_slug) / "expertise"
        if expertise_dir.exists():
            for jsonl_file in expertise_dir.glob("*.jsonl"):
                count += sum(1 for line in jsonl_file.read_text().splitlines() if line.strip())
    return JSONResponse({"count": count})


@router.post("/records/delete")
async def delete_record_action(
    request: Request,
    project: str = Form(...),
    domain: str = Form(...),
    record_id: str = Form(...),
) -> Response:
    ref = parse_project_ref(project)
    if ref:
        org_slug, project_slug = ref
        m_dir = mulch_dir(org_slug, project_slug)
        await delete_record(m_dir, domain, record_id)
    return RedirectResponse(f"/admin/p/{project}/records", status_code=303)


@router.post("/records/bulk-delete")
async def bulk_delete_records_action(
    request: Request,
    project: str = Form(...),
    items: list[str] = Form(...),
) -> Response:
    ref = parse_project_ref(project)
    if ref:
        org_slug, project_slug = ref
        m_dir = mulch_dir(org_slug, project_slug)
        for item in items:
            try:
                parsed = json.loads(item)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(parsed, dict):
                continue
            domain = parsed.get("domain")
            record_id = parsed.get("id")
            if not isinstance(domain, str) or not domain or not isinstance(record_id, str) or not record_id:
                continue
            await delete_record(m_dir, domain, record_id)
    return RedirectResponse(f"/admin/p/{project}/records", status_code=303)


@router.post("/records/edit")
async def edit_record_action(
    request: Request,
    project: str = Form(...),
    domain: str = Form(...),
    record_id: str = Form(...),
    field: str = Form(...),
    value: str = Form(""),
) -> Response:
    ref = parse_project_ref(project)
    if ref:
        org_slug, project_slug = ref
        m_dir = mulch_dir(org_slug, project_slug)
        await edit_record(m_dir, domain, record_id, {field: value.strip()})
    return RedirectResponse(f"/admin/p/{project}/records", status_code=303)


@router.get("/p/{org_slug}/{project_slug}/records")
async def records_page(request: Request, org_slug: str, project_slug: str) -> Response:
    project = await resolve_project_by_slugs(org_slug, project_slug)
    if project is None:
        return Response(status_code=404)

    domains_data: list[dict] = []
    expertise_dir = mulch_dir(org_slug, project_slug) / "expertise"
    if expertise_dir.exists():
        for jsonl_file in sorted(expertise_dir.glob("*.jsonl")):
            records = await read_domain_records(jsonl_file)
            if records:
                domains_data.append({"name": jsonl_file.stem, "records": records})

    total_record_count = sum(len(d["records"]) for d in domains_data)
    all_projects = await Project.all().order_by("org__slug", "slug").prefetch_related("org")

    response = templates.TemplateResponse(
        request,
        "records.html",
        {
            "active": "records",
            "project": project,
            "all_projects": all_projects,
            "active_tab": "records",
            "tab_path": "records",
            "domains": domains_data,
            "total_record_count": total_record_count,
        },
    )
    set_last_project_cookie(response, org_slug, project_slug)
    return response
