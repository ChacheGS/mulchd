from authlib.integrations.starlette_client import OAuth

from .config import settings

oauth = OAuth()

if settings.github_client_id and settings.github_client_secret:
    oauth.register(
        name="github",
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        client_kwargs={"scope": "user:email"},
    )

if (
    settings.oidc_discovery_url
    and settings.oidc_client_id
    and settings.oidc_client_secret
):
    oauth.register(
        name="oidc",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        server_metadata_url=settings.oidc_discovery_url,
        client_kwargs={"scope": "openid email profile"},
    )


def get_configured_providers() -> list[tuple[str, str]]:
    """Return (key, display_name) for each configured provider."""
    providers = []
    if settings.github_client_id and settings.github_client_secret:
        providers.append(("github", "GitHub"))
    if (
        settings.oidc_discovery_url
        and settings.oidc_client_id
        and settings.oidc_client_secret
    ):
        providers.append(("oidc", settings.oidc_display_name))
    return providers
