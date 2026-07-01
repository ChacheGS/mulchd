import hashlib
import secrets
from dataclasses import dataclass

from .models import Organization, Project, Role, User, UserMembership


@dataclass
class AuthContext:
    user: User
    project: Project
    org: Organization
    role: Role


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def validate_token(token: str) -> User | None:
    return await User.filter(token_hash=_hash_token(token), active=True).first()


async def resolve_project(org_slug: str, project_slug: str) -> Project | None:
    return await (
        Project.filter(slug=project_slug, org__slug=org_slug)
        .select_related("org")
        .first()
    )


async def check_membership(user: User, project: Project, min_role: Role = Role.READER) -> Role | None:
    """Return the user's role in the project, or None if they have no access."""
    membership = await UserMembership.filter(user=user, project=project).first()
    if membership is None:
        return None
    role_order = [Role.READER, Role.WRITER, Role.ADMIN]
    if role_order.index(membership.role) >= role_order.index(min_role):
        return membership.role
    return None


async def authenticate(token: str, org_slug: str, project_slug: str) -> AuthContext | None:
    user = await validate_token(token)
    if user is None:
        return None

    project = await resolve_project(org_slug, project_slug)
    if project is None:
        return None

    role = await check_membership(user, project)
    if role is None:
        return None

    return AuthContext(user=user, project=project, org=project.org, role=role)


def generate_token() -> str:
    return secrets.token_urlsafe(32)


async def create_user(username: str, display_name: str) -> tuple[User, str]:
    token = generate_token()
    user = await User.create(
        username=username,
        display_name=display_name,
        token_hash=_hash_token(token),
    )
    return user, token
