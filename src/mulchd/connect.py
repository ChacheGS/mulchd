from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer

from .auth import authenticate_global_token, create_project_token
from .config import settings
from .models import Project, ProjectToken, User, UserMembership

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

_CONNECT_COOKIE = "mulchd_connect"
_REMEMBER_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _signer() -> URLSafeSerializer:
    return URLSafeSerializer(settings.secret_key, salt="connect")


def _slug_to_env(s: str) -> str:
    return s.upper().replace("-", "_")


def build_connect_snippets(base_url: str, org: str, project: str, token: str) -> dict:
    env_var = f"MULCHD_TOKEN_{_slug_to_env(org)}_{_slug_to_env(project)}"
    mcp_json = (
        '{\n'
        '  "mcpServers": {\n'
        '    "mulchd": {\n'
        '      "type": "http",\n'
        f'      "url": "{base_url}/mcp",\n'
        f'      "headers": {{ "Authorization": "Bearer ${{{env_var}}}" }}\n'
        '    }\n'
        '  }\n'
        '}'
    )
    settings_local = (
        '{\n'
        '  "enabledMcpServersJson": ["mulchd"],\n'
        '  "env": {\n'
        f'    "{env_var}": "{token}"\n'
        '  }\n'
        '}'
    )
    desktop = (
        '{\n'
        '  "mcpServers": {\n'
        f'    "mulchd-{org}-{project}": {{\n'
        '      "command": "npx",\n'
        f'      "args": ["-y", "mcp-remote@latest", "{base_url}/mcp",\n'
        f'               "--header", "Authorization:${{{env_var}}}"],\n'
        f'      "env": {{ "{env_var}": "Bearer {token}" }}\n'
        '    }}\n'
        '  }\n'
        '}'
    )
    return {"mcp_json": mcp_json, "settings_local": settings_local, "desktop": desktop}
