"""Configuration management."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "feishu-paper-analyzer"
    app_env: str = "development"
    database_url: str = "sqlite:///./paper_analyzer.db"
    run_mode: Literal["webhook", "local_polling", "hybrid"] = "hybrid"

    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_base_token: str = ""
    feishu_table_id: str = ""
    webhook_shared_secret: str = Field(default="change-me", alias="WEBHOOK_SHARED_SECRET")

    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"

    job_timeout_sec: int = 900
    max_pdf_mb: int = 30
    worker_poll_interval_sec: float = 2.0
    worker_concurrency: int = 3
    local_poll_interval_sec: float = 10.0
    llm_request_timeout_sec: int = 120
    llm_max_chunk_chars: int = 12000
    llm_max_evidence_chars: int = 30000
    pdf_text_threshold: int = 1200
    llm_debug_enabled: bool = True
    llm_log_full_prompts: bool = True
    llm_log_preview_chars: int = 800

    @property
    def webhook_enabled(self) -> bool:
        return self.run_mode in {"webhook", "hybrid"}

    @property
    def local_polling_enabled(self) -> bool:
        return self.run_mode in {"local_polling", "hybrid"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings instance."""

    return Settings()
