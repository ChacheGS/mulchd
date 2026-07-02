from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from .auth import authenticate_global_token, create_project_token
from .models import Project, ProjectToken, User, UserMembership

router = APIRouter(prefix="/api", tags=["self-service"])
_security = HTTPBearer()


# ---------------------------------------------------------------------------
# Auth dependency — global token only
# ---------------------------------------------------------------------------


async def get_global_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> User:
    user = await authenticate_global_token(credentials.credentials)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or inactive global token. Project-scoped tokens are not accepted here.",
        )
    return user


async def _get_accessible_project(user: User, org_slug: str, project_slug: str) -> Project:
    project = (
        await Project.filter(slug=project_slug, org__slug=org_slug)
        .select_related("org")
        .first()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    membership = await UserMembership.filter(user=user, project=project).first()
    if membership is None:
        raise HTTPException(status_code=403, detail="No access to this project")
    return project


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class OrgOut(BaseModel):
    slug: str
    display_name: str


class ProjectOut(BaseModel):
    slug: str
    display_name: str
    knowledge_language: str | None = None


class ProjectAccessOut(BaseModel):
    org: OrgOut
    project: ProjectOut
    role: str


class TokenCreatedOut(BaseModel):
    id: int
    token: str  # raw value — shown once, not stored
    label: str
    created_at: datetime


class TokenOut(BaseModel):
    id: int
    label: str
    created_at: datetime


class MintTokenRequest(BaseModel):
    label: str = ""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/me/projects", response_model=list[ProjectAccessOut])
async def list_my_projects(user: User = Depends(get_global_user)):
    memberships = (
        await UserMembership.filter(user=user).select_related("project__org").all()
    )
    return [
        ProjectAccessOut(
            org=OrgOut(slug=m.project.org.slug, display_name=m.project.org.display_name),
            project=ProjectOut(slug=m.project.slug, display_name=m.project.display_name, knowledge_language=m.project.knowledge_language),
            role=m.role,
        )
        for m in memberships
    ]


@router.post("/projects/{org}/{project}/tokens", response_model=TokenCreatedOut, status_code=201)
async def mint_project_token(
    org: str,
    project: str,
    body: MintTokenRequest,
    user: User = Depends(get_global_user),
):
    proj = await _get_accessible_project(user, org, project)
    pt, raw_token = await create_project_token(user, proj, label=body.label)
    return TokenCreatedOut(id=pt.id, token=raw_token, label=pt.label, created_at=pt.created_at)


@router.get("/projects/{org}/{project}/tokens", response_model=list[TokenOut])
async def list_project_tokens(
    org: str,
    project: str,
    user: User = Depends(get_global_user),
):
    proj = await _get_accessible_project(user, org, project)
    tokens = await ProjectToken.filter(user=user, project=proj, active=True).all()
    return [TokenOut(id=t.id, label=t.label, created_at=t.created_at) for t in tokens]


@router.delete("/projects/{org}/{project}/tokens/{token_id}", status_code=204)
async def revoke_project_token(
    org: str,
    project: str,
    token_id: int,
    user: User = Depends(get_global_user),
):
    proj = await _get_accessible_project(user, org, project)
    updated = await ProjectToken.filter(
        id=token_id, user=user, project=proj, active=True
    ).update(active=False)
    if not updated:
        raise HTTPException(status_code=404, detail="Token not found")
