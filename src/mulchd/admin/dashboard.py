from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from ._shared import require_admin

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/")
async def root_redirect() -> RedirectResponse:
    return RedirectResponse("/admin/activity", status_code=302)
