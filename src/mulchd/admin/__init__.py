from fastapi import APIRouter

from .activity import router as activity_router
from .audit import router as audit_router
from .dashboard import router as dashboard_router
from .invites import router as invites_router
from .memberships import router as memberships_router
from .orgs import router as orgs_router
from .project_tokens import router as project_tokens_router
from .projects import router as projects_router
from .records_view import router as records_router
from .usage_api import router as usage_router
from .users import router as users_router

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(dashboard_router)
router.include_router(usage_router)
router.include_router(users_router)
router.include_router(orgs_router)
router.include_router(projects_router)
router.include_router(invites_router)
router.include_router(memberships_router)
router.include_router(project_tokens_router)
router.include_router(records_router)
router.include_router(audit_router)
router.include_router(activity_router)
