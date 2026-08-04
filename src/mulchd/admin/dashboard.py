from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ..models import Organization, Project, User, UserMembership
from ._shared import require_admin, templates

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/")
async def dashboard(request: Request) -> Response:
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "active": "dashboard",
            "stats": {
                "users": await User.filter(active=True).count(),
                "orgs": await Organization.all().count(),
                "projects": await Project.all().count(),
                "memberships": await UserMembership.all().count(),
            },
        },
    )
