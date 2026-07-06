from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    data_path: Path = Path(".mulch")
    db_url: str = "sqlite://mulchd.db"
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False
    secret_key: str  # required — set MULCHD_SECRET_KEY
    admin_password: str  # required — set MULCHD_ADMIN_PASSWORD
    admin_contact: str | None = (
        None  # MULCHD_ADMIN_CONTACT — shown in /connect portal and tier1 setup instructions
    )
    base_url: str | None = None  # MULCHD_BASE_URL — derived from host+port if unset

    model_config = {"env_file": ".env", "env_prefix": "MULCHD_"}

    @property
    def resolved_base_url(self) -> str:
        if self.base_url:
            return self.base_url.rstrip("/")
        return f"http://{self.host}:{self.port}"


settings = Settings()  # type: ignore[call-arg]

TORTOISE_ORM = {
    "connections": {"default": settings.db_url},
    "apps": {
        "models": {
            "models": ["mulchd.models", "aerich.models"],
            "default_connection": "default",
        }
    },
}
