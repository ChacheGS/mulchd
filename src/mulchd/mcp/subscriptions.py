from __future__ import annotations

from typing import Any


class SubscriptionRegistry:
    """
    Maps domain names to {session_id: session_proxy} for active subscribers.

    Keyed on the connection-stable mcp-session-id string, not the ServerSession
    object's Python identity — mcp v2 mints a fresh ServerSession proxy for
    every inbound message, even within one physical connection, so identity-based
    keying (or identity-based exclusion) silently stops matching the same
    logical subscriber from one message to the next. A captured proxy stays
    usable for sending after its handler returns (it holds the connection,
    not the request), so the last-seen proxy for a session-id is a valid
    delivery target even when it wasn't the one that triggered the notification.

    Sessions register when they touch a domain. On any mutating tool call the
    registry fans out notifications to all other subscribers. Cleanup is lazy:
    failed sends discard the dead session-id.
    """

    def __init__(self) -> None:
        self._subs: dict[str, dict[str, Any]] = {}

    def register(self, session_id: str, session: Any, domain: str) -> None:
        self._subs.setdefault(domain, {})[session_id] = session

    def unregister(self, session_id: str, domain: str) -> None:
        if domain in self._subs:
            self._subs[domain].pop(session_id, None)

    def unregister_session(self, session_id: str) -> None:
        for subs in self._subs.values():
            subs.pop(session_id, None)

    def subscribers_for(self, domain: str, exclude: str) -> dict[str, Any]:
        return {sid: s for sid, s in self._subs.get(domain, {}).items() if sid != exclude}


registry = SubscriptionRegistry()
