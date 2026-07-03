from contextvars import ContextVar

from ..auth import AuthContext

_ctx: ContextVar[AuthContext | None] = ContextVar("auth_context", default=None)
