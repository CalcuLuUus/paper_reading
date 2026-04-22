"""Database helpers."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from paper_analyzer.config import get_settings


def _connect_args(database_url: str) -> dict[str, object]:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


@lru_cache(maxsize=1)
def get_engine():
    settings = get_settings()
    return create_engine(
        settings.database_url,
        future=True,
        connect_args=_connect_args(settings.database_url),
    )


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(bind=get_engine(), expire_on_commit=False, class_=Session)


def get_session() -> Iterator[Session]:
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def init_database() -> None:
    from paper_analyzer.models import Base

    engine = get_engine()
    Base.metadata.create_all(engine)
    _migrate_analysis_jobs_table(engine)


def _migrate_analysis_jobs_table(engine) -> None:
    inspector = inspect(engine)
    if "analysis_jobs" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("analysis_jobs")}
    needs_rebuild = _needs_analysis_jobs_rebuild(engine)
    if needs_rebuild:
        _rebuild_analysis_jobs_table(engine, columns)
        return

    alter_statements: list[str] = []
    if "trigger_mode" not in columns:
        alter_statements.append(
            "ALTER TABLE analysis_jobs ADD COLUMN trigger_mode VARCHAR(32) NOT NULL DEFAULT 'webhook'"
        )
    if "force_rerun" not in columns:
        alter_statements.append(
            "ALTER TABLE analysis_jobs ADD COLUMN force_rerun BOOLEAN NOT NULL DEFAULT 0"
        )
    if not alter_statements:
        return

    with engine.begin() as connection:
        for statement in alter_statements:
            connection.execute(text(statement))


def _needs_analysis_jobs_rebuild(engine) -> bool:
    if engine.dialect.name != "sqlite":
        return False
    with engine.connect() as connection:
        sql = connection.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='analysis_jobs'")
        ).scalar_one_or_none()
    if not sql:
        return False
    normalized = " ".join(str(sql).lower().split())
    return "unique (record_id, source_hash)" in normalized


def _rebuild_analysis_jobs_table(engine, columns: set[str]) -> None:
    from paper_analyzer.models import Base

    copy_columns = [
        "id",
        "base_token",
        "table_id",
        "record_id",
        "source_hash",
        "status",
        "attempts",
        "error",
        "source_type",
        "source_meta_json",
        "result_json",
        "requested_at",
        "started_at",
        "finished_at",
    ]

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE analysis_jobs RENAME TO analysis_jobs_legacy"))
        legacy_indexes = connection.execute(text("PRAGMA index_list('analysis_jobs_legacy')")).mappings()
        for index in legacy_indexes:
            index_name = index["name"]
            if str(index_name).startswith("sqlite_autoindex"):
                continue
            connection.execute(text(f'DROP INDEX "{index_name}"'))
        Base.metadata.create_all(connection)
        insert_columns = [
            "id",
            "base_token",
            "table_id",
            "record_id",
            "source_hash",
            "status",
            "attempts",
            "error",
            "source_type",
            "trigger_mode",
            "force_rerun",
            "source_meta_json",
            "result_json",
            "requested_at",
            "started_at",
            "finished_at",
        ]
        select_expressions: list[str] = []
        for column in insert_columns:
            if column == "trigger_mode":
                select_expressions.append("'webhook' AS trigger_mode")
            elif column == "force_rerun":
                select_expressions.append("0 AS force_rerun")
            elif column in copy_columns and column in columns:
                select_expressions.append(column)
        insert_sql = (
            f"INSERT INTO analysis_jobs ({', '.join(insert_columns)}) "
            f"SELECT {', '.join(select_expressions)} FROM analysis_jobs_legacy"
        )
        connection.execute(text(insert_sql))
        connection.execute(text("DROP TABLE analysis_jobs_legacy"))
