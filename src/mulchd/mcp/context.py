from contextvars import ContextVar

from ..auth import AuthContext
from ..models import User

_ctx: ContextVar[AuthContext | None] = ContextVar("auth_context", default=None)
_global_ctx: ContextVar[User | None] = ContextVar("global_auth_context", default=None)
