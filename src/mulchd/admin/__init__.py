from fastapi import APIRouter

from .auth import router as auth_router
from .dashboard import router as dashboard_router
from .memberships import router as memberships_router
from .orgs import router as orgs_router
from .project_tokens import router as project_tokens_router
from .projects import router as projects_router
from .users import router as users_router

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(auth_router)
router.include_router(dashboard_router)
router.include_router(users_router)
router.include_router(orgs_router)
router.include_router(projects_router)
router.include_router(memberships_router)
router.include_router(project_tokens_router)
