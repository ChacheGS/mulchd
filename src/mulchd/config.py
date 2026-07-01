from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    data_path: Path = Path(".mulch")
    db_url: str = "sqlite://mulchd.db"
    host: str = "0.0.0.0"
    port: int = 8000
    secret_key: str  # required — set MULCHD_SECRET_KEY
    admin_password: str  # required — set MULCHD_ADMIN_PASSWORD

    model_config = {"env_file": ".env", "env_prefix": "MULCHD_"}


settings = Settings()  # type: ignore[call-arg]  # pydantic-settings resolves from env at runtime

TORTOISE_ORM = {
    "connections": {"default": settings.db_url},
    "apps": {
        "models": {
            "models": ["server.models", "aerich.models"],
            "default_connection": "default",
        }
    },
}
