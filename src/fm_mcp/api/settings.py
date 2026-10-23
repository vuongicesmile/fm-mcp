"""Settings used only by the Workflow Automation API runtime."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class APISettings(BaseSettings):
    """Database and identity settings. Do not supply DATABASE_URL to MCP runtime."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://fm_user:change_me@localhost:5432/fm_central"
    environment: str = "development"
    workflow_api_audience: str = "fm-workflow-api"
    auth_jwt_secret: str | None = None
    auth_jwt_algorithm: str = "HS256"
    smtp_host: str = Field(default="localhost", validation_alias="FM_SMTP_HOST")
    smtp_port: int = Field(default=1025, validation_alias="FM_SMTP_PORT")
    smtp_timeout_seconds: int = Field(default=15, validation_alias="FM_SMTP_TIMEOUT_SECONDS")
    smtp_starttls: bool = Field(default=False, validation_alias="FM_SMTP_STARTTLS")
    smtp_username: str | None = Field(default=None, validation_alias="FM_SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, validation_alias="FM_SMTP_PASSWORD")
    smtp_from_address: str = Field(default="fm-workflow@example.test", validation_alias="FM_SMTP_FROM_ADDRESS")
    smtp_max_attempts: int = Field(default=3, validation_alias="FM_SMTP_MAX_ATTEMPTS")
    smtp_retry_delay_seconds: int = Field(default=60, validation_alias="FM_SMTP_RETRY_DELAY_SECONDS")
    request_notification_email: str | None = Field(default=None, validation_alias="FM_REQUEST_NOTIFICATION_EMAIL")


@lru_cache
def get_api_settings() -> APISettings:
    return APISettings()


api_settings = get_api_settings()
