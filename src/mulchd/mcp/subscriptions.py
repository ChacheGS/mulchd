from __future__ import annotations

from typing import Any


def _domain_key(org_slug: str, project_slug: str, domain: str) -> str:
    return f"{org_slug}/{project_slug}/{domain}"


class SubscriptionRegistry:
    """
    Maps (org, project, domain) keys to {session_id: session_proxy} for active subscribers.

    Two independent keying fixes live here, found at two different points in this
    project's history:

    1. Keyed on the connection-stable mcp-session-id string, not the ServerSession
       object's Python identity — mcp v2 mints a fresh ServerSession proxy for
       every inbound message, even within one physical connection, so identity-based
       keying (or identity-based exclusion) silently stops matching the same
       logical subscriber from one message to the next. A captured proxy stays
       usable for sending after its handler returns (it holds the connection,
       not the request), so the last-seen proxy for a session-id is a valid
       delivery target even when it wasn't the one that triggered the notification.
    2. Keyed on (org_slug, project_slug, domain), not domain name alone — two
       different projects with a same-named domain (a plausible, common name like
       "infra") would otherwise cross-notify each other, since a bare domain name
       is not unique across projects.

    Sessions register when they touch a domain. On any mutating tool call the
    registry fans out notifications to all other subscribers. Cleanup is lazy:
    failed sends discard the dead session-id.
    """

    def __init__(self) -> None:
        self._subs: dict[str, dict[str, Any]] = {}

    def register(
        self, session_id: str, session: Any, org_slug: str, project_slug: str, domain: str
    ) -> None:
        key = _domain_key(org_slug, project_slug, domain)
        self._subs.setdefault(key, {})[session_id] = session

    def unregister(self, session_id: str, org_slug: str, project_slug: str, domain: str) -> None:
        key = _domain_key(org_slug, project_slug, domain)
        if key in self._subs:
            self._subs[key].pop(session_id, None)

    def unregister_session(self, session_id: str) -> None:
        for subs in self._subs.values():
            subs.pop(session_id, None)

    def subscribers_for(
        self, org_slug: str, project_slug: str, domain: str, exclude: str
    ) -> dict[str, Any]:
        key = _domain_key(org_slug, project_slug, domain)
        return {sid: s for sid, s in self._subs.get(key, {}).items() if sid != exclude}


registry = SubscriptionRegistry()
