from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = "change-me-in-production"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/transactions_db"
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    PARTNER_API_URL: str = "http://partner-mock:8001"
    PARTNER_API_TIMEOUT: float = 10.0
    API_AUTH_USERNAME: str = Field(default="admin", min_length=1)
    API_AUTH_PASSWORD: str = Field(default="admin", min_length=1)
    API_AUTH_TOKEN_EXPIRE_SECONDS: int = Field(default=3600, gt=0)
    API_AUTH_TOKEN: str = Field(default="dev-token", min_length=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
