import asyncio
import json
import logging
from typing import Any, cast

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from ..domains import mulch_dir
from ..mulch import MulchError, delete_record, edit_record
from ..records import read_domain_records
from ._shared import (
    parse_project_ref,
    require_admin,
    resolve_project_by_slugs,
    set_last_project_cookie,
    templates,
)

_log = logging.getLogger("mulchd")

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
        pairs: list[tuple[str, str]] = []
        for item in items:
            try:
                parsed = json.loads(item)
            except json.JSONDecodeError, TypeError:
                continue
            if not isinstance(parsed, dict):
                continue
            parsed_obj = cast(
                dict[str, Any], parsed
            )  # json.loads returns Any; narrowed shape isn't known to pyright
            domain = parsed_obj.get("domain")
            record_id = parsed_obj.get("id")
            if (
                not isinstance(domain, str)
                or not domain
                or not isinstance(record_id, str)
                or not record_id
            ):
                continue
            pairs.append((domain, record_id))

        # ml archive is safe under concurrent writes to the same domain file
        # (verified directly against the live binary — concurrent archive
        # calls on the same file each correctly touch only their own record,
        # no corruption or lost writes). Run the batch concurrently rather
        # than one ml subprocess spawn at a time, and let one bad record
        # (e.g. already deleted) fail without blocking the rest of the batch.
        results = await asyncio.gather(
            *(delete_record(m_dir, domain, record_id) for domain, record_id in pairs),
            return_exceptions=True,
        )
        for (domain, record_id), result in zip(pairs, results):
            if isinstance(result, MulchError):
                _log.warning("bulk delete failed for %s/%s: %s", domain, record_id, result)
            elif isinstance(result, BaseException):
                raise result
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

    domains_data: list[dict[str, Any]] = []
    expertise_dir = mulch_dir(org_slug, project_slug) / "expertise"
    if expertise_dir.exists():
        for jsonl_file in sorted(expertise_dir.glob("*.jsonl")):
            records = await read_domain_records(jsonl_file)
            if records:
                domains_data.append({"name": jsonl_file.stem, "records": records})

    total_record_count = sum(len(d["records"]) for d in domains_data)

    response = templates.TemplateResponse(
        request,
        "records.html",
        {
            "active": "records",
            "project": project,
            "active_tab": "records",
            "tab_path": "records",
            "domains": domains_data,
            "total_record_count": total_record_count,
        },
    )
    set_last_project_cookie(response, org_slug, project_slug)
    return response
