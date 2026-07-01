import hashlib
import secrets
from dataclasses import dataclass

from .models import Organization, Project, ProjectToken, Role, User, UserMembership


@dataclass
class AuthContext:
    user: User
    project: Project
    org: Organization
    role: Role


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_token() -> str:
    return secrets.token_urlsafe(32)


async def authenticate_project_token(token: str) -> AuthContext | None:
    """
    Resolve a project-scoped token to an AuthContext.

    Three things must hold: the token exists and is active, the user is active,
    and a UserMembership still exists for that user+project pair. Role is read
    from the membership at request time so changes take effect immediately.
    """
    pt = (
        await ProjectToken.filter(token_hash=_hash_token(token), active=True)
        .select_related("user", "project__org")
        .first()
    )
    if pt is None or not pt.user.active:
        return None

    membership = await UserMembership.filter(user=pt.user, project=pt.project).first()
    if membership is None:
        return None

    return AuthContext(user=pt.user, project=pt.project, org=pt.project.org, role=membership.role)


async def authenticate_global_token(token: str) -> User | None:
    """
    Resolve a global (user-level) token. Used only by self-service API endpoints
    (list projects, mint project tokens). Rejected on /sse.
    """
    return await User.filter(token_hash=_hash_token(token), active=True).first()


async def create_user(username: str, display_name: str) -> tuple[User, str]:
    token = generate_token()
    user = await User.create(
        username=username,
        display_name=display_name,
        token_hash=_hash_token(token),
    )
    return user, token


async def create_project_token(user: User, project: Project, label: str = "") -> tuple[ProjectToken, str]:
    token = generate_token()
    pt = await ProjectToken.create(
        user=user,
        project=project,
        token_hash=_hash_token(token),
        label=label,
    )
    return pt, token
