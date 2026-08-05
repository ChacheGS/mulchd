from contextvars import ContextVar

from ..auth import AuthContext

auth_ctx: ContextVar[AuthContext | None] = ContextVar("auth_context", default=None)
session_id_ctx: ContextVar[str | None] = ContextVar("session_id", default=None)
