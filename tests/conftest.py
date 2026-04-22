from __future__ import annotations

from pathlib import Path

import pytest

from paper_analyzer.config import get_settings
from paper_analyzer.database import get_engine, get_session_factory


@pytest.fixture()
def test_env(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("FEISHU_APP_ID", "cli_test")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
    monkeypatch.setenv("FEISHU_BASE_TOKEN", "base_test")
    monkeypatch.setenv("FEISHU_TABLE_ID", "table_test")
    monkeypatch.setenv("WEBHOOK_SHARED_SECRET", "hook_secret")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    yield

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

