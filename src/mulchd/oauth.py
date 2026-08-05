import os
import re
from typing import NamedTuple, TypedDict

from authlib.integrations.starlette_client import OAuth

from .config import settings

oauth = OAuth()


class ProviderInfo(NamedTuple):
    key: str
    display_name: str
    logo_url: str | None


class _OidcProviderConfig(TypedDict):
    slug: str
    discovery_url: str
    client_id: str
    client_secret: str
    display_name: str
    logo_url: str | None


_OIDC_DISCOVERY_RE = re.compile(r"^MULCHD_OIDC_([A-Z0-9_]+)_DISCOVERY_URL$")


def _discover_oidc_providers() -> list[_OidcProviderConfig]:
    """Scan the process environment for MULCHD_OIDC_{SLUG}_* vars and return one
    entry per fully-configured provider (discovery URL + client id + secret all
    present), sorted by slug for stable ordering. A provider missing client_id or
    client_secret is skipped rather than raising, the same way a single
    misconfigured provider used to just not register before this became
    multi-provider."""
    found: list[_OidcProviderConfig] = []
    for env_key, discovery_url in os.environ.items():
        m = _OIDC_DISCOVERY_RE.match(env_key)
        if not m:
            continue
        slug_upper = m.group(1)
        client_id = os.environ.get(f"MULCHD_OIDC_{slug_upper}_CLIENT_ID")
        client_secret = os.environ.get(f"MULCHD_OIDC_{slug_upper}_CLIENT_SECRET")
        if not client_id or not client_secret:
            continue
        slug = slug_upper.lower()
        display_name = os.environ.get(f"MULCHD_OIDC_{slug_upper}_DISPLAY_NAME") or slug.replace("_", " ").title()
        found.append(
            {
                "slug": slug,
                "discovery_url": discovery_url,
                "client_id": client_id,
                "client_secret": client_secret,
                "display_name": display_name,
                "logo_url": os.environ.get(f"MULCHD_OIDC_{slug_upper}_LOGO_URL"),
            }
        )
    return sorted(found, key=lambda p: p["slug"])


if settings.github_client_id and settings.github_client_secret:
    oauth.register(  # pyright: ignore[reportUnknownMemberType]  # authlib's OAuth.register isn't fully typed
        name="github",
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        client_kwargs={"scope": "user:email"},
    )

for _p in _discover_oidc_providers():
    oauth.register(  # pyright: ignore[reportUnknownMemberType]  # authlib's OAuth.register isn't fully typed
        name=f"oidc_{_p['slug']}",
        client_id=_p["client_id"],
        client_secret=_p["client_secret"],
        server_metadata_url=_p["discovery_url"],
        client_kwargs={"scope": "openid email profile"},
    )


def get_configured_providers() -> list[ProviderInfo]:
    """Return one ProviderInfo per configured provider: GitHub first (if
    configured), then OIDC providers sorted by slug."""
    providers: list[ProviderInfo] = []
    if settings.github_client_id and settings.github_client_secret:
        providers.append(ProviderInfo(key="github", display_name="GitHub", logo_url=None))
    for p in _discover_oidc_providers():
        providers.append(
            ProviderInfo(key=f"oidc_{p['slug']}", display_name=p["display_name"], logo_url=p["logo_url"])
        )
    return providers
