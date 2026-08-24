"""App configuration via pydantic-settings — reads from .env"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    environment: str = "development"
    log_level: str = "INFO"

    # LLM
    anthropic_api_key: str = ""

    # Research APIs
    proxycurl_api_key: str = ""
    wappalyzer_api_key: str = ""
    serper_api_key: str = ""
    brave_api_key: str = ""

    # Database
    database_url: str = "postgresql://app:app@localhost:5432/sales_agent"
    redis_url: str = "redis://localhost:6379"

    # AWS
    aws_region: str = "ap-southeast-2"
    sqs_queue_url: str = ""


settings = Settings()