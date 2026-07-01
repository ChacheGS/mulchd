from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from ..models import Organization, Project, User, UserMembership
from ._shared import is_admin, redirect_login, templates

router = APIRouter()


@router.get("/")
async def dashboard(request: Request) -> Response:
    if not is_admin(request):
        return redirect_login()
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
