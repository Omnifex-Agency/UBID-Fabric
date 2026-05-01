"""UBID Fabric — Configuration (loaded from .env)"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://ubid_fabric:ubid_dev_2026@localhost:5432/ubid_fabric"
    redis_url: str = "redis://localhost:6379/0"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "DEBUG"
    conflict_window_seconds: int = 30
    reconciliation_interval_seconds: int = 21600
    max_saga_retries: int = 5
    idempotency_ttl_seconds: int = 604800  # 7 days

    # AI Integration
    ai_provider: str = "ollama"  # Default to local; switch to "gemini" for cloud
    ai_api_key: str = ""
    ai_base_url: str = "http://localhost:11434/v1"  # Default for Ollama
    ai_model: str = "llama3"  # or "gemini-1.5-flash"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
