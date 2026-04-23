"""Job queueing and processing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from paper_analyzer.clients.feishu import FeishuAPIError, FeishuClient
from paper_analyzer.config import Settings
from paper_analyzer.constants import (
    ERROR_FIELD,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    LAST_ANALYZED_AT_FIELD,
    PAPER_ID_FIELD,
    RUN_MODE_LOCAL_POLLING,
    RUN_MODE_WEBHOOK,
    SOURCE_HASH_FIELD,
    SOURCE_TYPE_FIELD,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_FIELD,
    STATUS_PENDING,
    STATUS_QUEUED,
    STATUS_RUNNING,
    TITLE_FIELD,
    TRIGGER_FIELDS,
    TRIGGER_MODE_LOCAL_POLLING,
    TRIGGER_MODE_WEBHOOK,
)
from paper_analyzer.models import AnalysisJob
from paper_analyzer.schemas import SourceSelection, WebhookPayload
from paper_analyzer.services.analysis import PaperAnalyzer
from paper_analyzer.services.source_loader import PaperSourceLoader, SourceSelectionError, resolve_source_selection
from paper_analyzer.utils import utcnow, utcnow_iso


@dataclass
class EnqueueResult:
    status: str
    job_id: int | None = None
    reason: str | None = None
    source_hash: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": self.status}
        if self.job_id is not None:
            payload["job_id"] = self.job_id
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.source_hash is not None:
            payload["source_hash"] = self.source_hash
        return payload


class JobService:
    """Enqueue and claim analysis jobs."""

    def __init__(self, session: Session, settings: Settings, feishu_client: FeishuClient):
        self.session = session
        self.settings = settings
        self.feishu_client = feishu_client

    def handle_webhook(self, payload: WebhookPayload) -> EnqueueResult:
        if not self.settings.webhook_enabled:
            raise ValueError("webhook mode disabled")
        self._ensure_scoped(payload)

        if payload.changed_fields and not (set(payload.changed_fields) & TRIGGER_FIELDS):
            return EnqueueResult(status="ignored", reason="non_trigger_fields")

        record = self.feishu_client.get_record(payload.base_token, payload.table_id, payload.record_id)
        return self.enqueue_record(
            base_token=payload.base_token,
            table_id=payload.table_id,
            record_id=payload.record_id,
            record_fields=record.get("fields", {}),
            trigger_mode=TRIGGER_MODE_WEBHOOK,
            force_rerun=False,
        )

    def enqueue_record(
        self,
        *,
        base_token: str,
        table_id: str,
        record_id: str,
        record_fields: dict[str, Any],
        trigger_mode: str,
        force_rerun: bool,
    ) -> EnqueueResult:
        try:
            source = resolve_source_selection(record_fields)
        except SourceSelectionError as exc:
            self._mark_record_failed(base_token, table_id, record_id, str(exc))
            return EnqueueResult(status="failed", reason="missing_source")

        existing = self._get_pending_job_by_source(record_id, source.source_hash)
        if existing:
            return EnqueueResult(
                status="duplicate",
                job_id=existing.id,
                reason="job_already_pending",
                source_hash=source.source_hash,
            )

        if (
            not force_rerun
            and record_fields.get(SOURCE_HASH_FIELD) == source.source_hash
            and record_fields.get(STATUS_FIELD) == STATUS_COMPLETED
        ):
            return EnqueueResult(status="skipped", reason="same_source_hash", source_hash=source.source_hash)

        latest = self._get_latest_job_by_source(record_id, source.source_hash)
        if latest and latest.status == JOB_STATUS_COMPLETED and not force_rerun:
            return EnqueueResult(
                status="skipped",
                job_id=latest.id,
                reason="job_already_completed",
                source_hash=source.source_hash,
            )

        job = AnalysisJob(
            base_token=base_token,
            table_id=table_id,
            record_id=record_id,
            source_hash=source.source_hash,
            status=JOB_STATUS_QUEUED,
            attempts=0,
            error=None,
            source_type=source.source_type,
            trigger_mode=trigger_mode,
            force_rerun=force_rerun,
            source_meta_json=source.model_dump_json(),
            result_json=None,
            requested_at=utcnow(),
            started_at=None,
            finished_at=None,
        )
        self.session.add(job)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            duplicate = self._get_pending_job_by_source(record_id, source.source_hash)
            return EnqueueResult(
                status="duplicate",
                job_id=duplicate.id if duplicate else None,
                reason="unique_constraint",
                source_hash=source.source_hash,
            )

        self.feishu_client.update_record(
            base_token,
            table_id,
            record_id,
            {STATUS_FIELD: STATUS_QUEUED, ERROR_FIELD: ""},
        )
        return EnqueueResult(status="queued", job_id=job.id, source_hash=source.source_hash)

    def claim_next_job(self) -> AnalysisJob | None:
        now = utcnow()
        with self.session.begin():
            self.session.execute(text("BEGIN IMMEDIATE"))
            row = self.session.execute(
                text(
                    """
                    SELECT id
                    FROM analysis_jobs
                    WHERE status = :status
                    ORDER BY requested_at ASC
                    LIMIT 1
                    """
                ),
                {"status": JOB_STATUS_QUEUED},
            ).fetchone()
            if row is None:
                return None

            job_id = int(row[0])
            self.session.execute(
                text(
                    """
                    UPDATE analysis_jobs
                    SET status = :running_status,
                        started_at = :started_at,
                        attempts = attempts + 1
                    WHERE id = :job_id
                    """
                ),
                {
                    "running_status": JOB_STATUS_RUNNING,
                    "started_at": now,
                    "job_id": job_id,
                },
            )

        job = self.session.get(AnalysisJob, job_id)
        if job is not None:
            self.session.refresh(job)
        return job

    def _get_latest_job_by_source(self, record_id: str, source_hash: str) -> AnalysisJob | None:
        return self.session.scalar(
            select(AnalysisJob)
            .where(AnalysisJob.record_id == record_id, AnalysisJob.source_hash == source_hash)
            .order_by(AnalysisJob.requested_at.desc())
            .limit(1)
        )

    def _get_pending_job_by_source(self, record_id: str, source_hash: str) -> AnalysisJob | None:
        return self.session.scalar(
            select(AnalysisJob)
            .where(
                AnalysisJob.record_id == record_id,
                AnalysisJob.source_hash == source_hash,
                AnalysisJob.status.in_([JOB_STATUS_QUEUED, JOB_STATUS_RUNNING]),
            )
            .order_by(AnalysisJob.requested_at.desc())
            .limit(1)
        )

    def _ensure_scoped(self, payload: WebhookPayload) -> None:
        if self.settings.feishu_base_token and payload.base_token != self.settings.feishu_base_token:
            raise ValueError("unexpected base_token")
        if self.settings.feishu_table_id and payload.table_id != self.settings.feishu_table_id:
            raise ValueError("unexpected table_id")

    def _mark_record_failed(self, base_token: str, table_id: str, record_id: str, message: str) -> None:
        self.feishu_client.update_record(
            base_token,
            table_id,
            record_id,
            {STATUS_FIELD: STATUS_FAILED, ERROR_FIELD: message},
        )


class JobProcessor:
    """Process a queued analysis job."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        feishu_client: FeishuClient,
        analyzer: PaperAnalyzer,
    ):
        self.session = session
        self.settings = settings
        self.feishu_client = feishu_client
        self.analyzer = analyzer
        self.source_loader = PaperSourceLoader(settings, feishu_client)

    def process(self, job: AnalysisJob) -> None:
        try:
            source = SourceSelection.model_validate_json(job.source_meta_json or "{}")
            record = self.feishu_client.get_record(job.base_token, job.table_id, job.record_id)
            fields = record.get("fields", {})
            title_hint = str(fields.get(TITLE_FIELD, "")).strip() or None
            self.feishu_client.update_record(
                job.base_token,
                job.table_id,
                job.record_id,
                {STATUS_FIELD: STATUS_RUNNING, ERROR_FIELD: ""},
            )
            document = self.source_loader.load(source, title_hint=title_hint)
            output = self.analyzer.analyze(document)
            writeback_fields = output.to_feishu_fields()
            writeback_fields.update(
                {
                    STATUS_FIELD: STATUS_COMPLETED,
                    ERROR_FIELD: "",
                    SOURCE_TYPE_FIELD: document.source_type,
                    SOURCE_HASH_FIELD: source.source_hash,
                    PAPER_ID_FIELD: source.paper_id or "",
                    LAST_ANALYZED_AT_FIELD: utcnow_iso(),
                }
            )
            self.feishu_client.update_record(
                job.base_token,
                job.table_id,
                job.record_id,
                writeback_fields,
            )
            job.status = JOB_STATUS_COMPLETED
            job.error = None
            job.result_json = output.model_dump_json(by_alias=True)
            job.finished_at = utcnow()
            self.session.commit()
        except Exception as exc:
            self._fail_job(job, exc)

    def _fail_job(self, job: AnalysisJob, exc: Exception) -> None:
        user_message = _format_job_error(exc)
        try:
            self.feishu_client.update_record(
                job.base_token,
                job.table_id,
                job.record_id,
                {STATUS_FIELD: STATUS_FAILED, ERROR_FIELD: user_message},
            )
        except FeishuAPIError:
            pass
        job.status = JOB_STATUS_FAILED
        job.error = user_message
        job.finished_at = utcnow()
        self.session.commit()


def _format_job_error(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return "分析失败：未知错误"
    return f"分析失败：{message}"


class LocalPollingScanner:
    """Scan records marked as pending analysis and enqueue them."""

    def __init__(self, session: Session, settings: Settings, feishu_client: FeishuClient):
        self.session = session
        self.settings = settings
        self.feishu_client = feishu_client
        self.job_service = JobService(session, settings, feishu_client)

    def scan(self) -> list[EnqueueResult]:
        if not self.settings.local_polling_enabled:
            raise ValueError("local polling mode disabled")

        results: list[EnqueueResult] = []
        for record in self.feishu_client.iter_records(
            self.settings.feishu_base_token,
            self.settings.feishu_table_id,
        ):
            fields = record.get("fields", {})
            if fields.get(STATUS_FIELD) != STATUS_PENDING:
                continue
            results.append(
                self.job_service.enqueue_record(
                    base_token=self.settings.feishu_base_token,
                    table_id=self.settings.feishu_table_id,
                    record_id=record["record_id"],
                    record_fields=fields,
                    trigger_mode=TRIGGER_MODE_LOCAL_POLLING,
                    force_rerun=True,
                )
            )
        return results
