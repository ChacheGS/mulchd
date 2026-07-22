from .models import InstanceEvent, InstanceEventCategory, Project, User


async def log_event(
    category: InstanceEventCategory,
    actor: User,
    subject_user: User | None = None,
    project: Project | None = None,
    detail: dict | None = None,
) -> InstanceEvent:
    """
    Record an account/access-level activity event. Blocking (not fire-and-forget)
    — this is a low-frequency, human-driven admin surface, unlike the existing
    fire-and-forget ToolCall recording in mcp/tier2.py, which exists specifically
    to avoid adding latency to every MCP tool call.
    """
    return await InstanceEvent.create(
        category=category,
        actor=actor,
        subject_user=subject_user,
        project=project,
        detail=detail,
    )


def describe_event(event: InstanceEvent) -> str:
    """
    Human-readable one-line description for the /admin/activity page.
    Expects event.actor, event.subject_user (if any), and event.project__org
    (if any) to already be fetched/select_related by the caller — this function
    does not perform any DB access itself.
    """
    detail = event.detail or {}
    subject_name = event.subject_user.username if event.subject_user else ""
    project_label = (
        f"{event.project.org.slug}/{event.project.slug}" if event.project else ""
    )

    if event.category == InstanceEventCategory.ADMIN_GRANTED:
        return f"Granted SUPERADMIN to {subject_name}"
    if event.category == InstanceEventCategory.ADMIN_REVOKED:
        return f"Revoked SUPERADMIN from {subject_name}"
    if event.category == InstanceEventCategory.MEMBERSHIP_ADDED:
        role = detail.get("role", "")
        return f"Added {subject_name} to {project_label} as {role}"
    if event.category == InstanceEventCategory.MEMBERSHIP_REMOVED:
        return f"Removed {subject_name} from {project_label}"
    if event.category == InstanceEventCategory.FIRST_LOGIN:
        provider = detail.get("provider", "")
        return f"First login ({provider})" if provider else "First login"
    if event.category == InstanceEventCategory.OAUTH_LINKED:
        provider = detail.get("provider", "")
        return f"Linked {provider} identity"
    if event.category == InstanceEventCategory.TOKEN_RESET:
        return f"Reset global token for {subject_name}"
    if event.category == InstanceEventCategory.ORG_CREATED:
        return f"Created org {detail.get('org_slug', '')}"
    if event.category == InstanceEventCategory.PROJECT_CREATED:
        return f"Created project {project_label}"
    if event.category == InstanceEventCategory.USER_CREATED:
        return f"Created user {subject_name}"
    if event.category == InstanceEventCategory.USER_DEACTIVATED:
        return f"Deactivated user {subject_name}"
    if event.category == InstanceEventCategory.INVITE_CREATED:
        role = detail.get("role", "")
        return f"Created invite link for {project_label} ({role})"
    if event.category == InstanceEventCategory.INVITE_REVOKED:
        return f"Revoked invite link for {project_label}"
    return str(event.category)
