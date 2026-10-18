"""Settings used only by the Workflow Automation API runtime."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class APISettings(BaseSettings):
    """Database and identity settings. Do not supply DATABASE_URL to MCP runtime."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://fm_user:change_me@localhost:5432/fm_central"
    environment: str = "development"
    workflow_api_audience: str = "fm-workflow-api"
    auth_jwt_secret: str | None = None
    auth_jwt_algorithm: str = "HS256"


@lru_cache
def get_api_settings() -> APISettings:
    return APISettings()


api_settings = get_api_settings()
