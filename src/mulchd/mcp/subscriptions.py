from __future__ import annotations

from typing import Any


class SubscriptionRegistry:
    """
    Maps domain names to sets of active ServerSession objects.

    Sessions register when they touch a domain. On any mutating tool call the
    registry fans out notifications to all other subscribers. Cleanup is lazy:
    failed sends discard the dead session.
    """

    def __init__(self) -> None:
        self._subs: dict[str, set[Any]] = {}

    def register(self, session: Any, domain: str) -> None:
        self._subs.setdefault(domain, set()).add(session)

    def unregister_session(self, session: Any) -> None:
        for subs in self._subs.values():
            subs.discard(session)

    def subscribers_for(self, domain: str, exclude: Any) -> set[Any]:
        return self._subs.get(domain, set()) - {exclude}


registry = SubscriptionRegistry()
