from paper_analyzer.config import get_settings
from paper_analyzer.constants import (
    ARXIV_FIELD,
    OUTPUT_ABSTRACT_TRANSLATION,
    STATUS_COMPLETED,
    STATUS_FIELD,
    STATUS_PENDING,
    TRIGGER_MODE_LOCAL_POLLING,
    TRIGGER_MODE_WEBHOOK,
)
from paper_analyzer.database import get_session_factory, init_database
from paper_analyzer.models import AnalysisJob
from paper_analyzer.schemas import PaperAnalysisOutput, PaperDocument, WebhookPayload
from paper_analyzer.services.analysis import PaperAnalyzer
from paper_analyzer.services.jobs import JobProcessor, JobService, LocalPollingScanner
from paper_analyzer.utils import utcnow
from paper_analyzer.clients.feishu import FeishuClient


class FakeFeishuClient(FeishuClient):
    def __init__(self, settings):
        super().__init__(settings)
        self.updates = []
        self.record_fields = {
            "论文标题/备注": "Test Paper",
            ARXIV_FIELD: "https://arxiv.org/abs/2401.01234",
        }
        self.records = [{"record_id": "rec1", "fields": self.record_fields}]

    def get_tenant_access_token(self):
        return "token"

    def get_record(self, base_token, table_id, record_id):
        return {"record_id": record_id, "fields": self.record_fields}

    def update_record(self, base_token, table_id, record_id, fields):
        self.updates.append(fields)
        self.record_fields.update(fields)
        return {"record_id": record_id, "fields": self.record_fields}

    def iter_records(self, base_token, table_id, page_size=100):
        return self.records


class FakeAnalyzer(PaperAnalyzer):
    def __init__(self):
        pass

    def analyze(self, document):
        return PaperAnalysisOutput(
            abstract_translation="中文摘要",
            motivation="动机",
            method_design="设计",
            comparison="| 方法 | 优点 |\n| --- | --- |\n| Ours | 更好 |",
            experimental_performance="结果",
            learning_and_application="应用",
            summary="a) 核心思想：提升效果\nb) 速记版 Pipeline：1. 输入 2. 编码 3. 输出",
            keywords_domain="领域: 机器学习\n关键词: arxiv; llm",
        )


def test_job_service_enqueue_and_processor_success(test_env):
    settings = get_settings()
    init_database()
    session = get_session_factory()()
    feishu = FakeFeishuClient(settings)
    service = JobService(session, settings, feishu)

    result = service.handle_webhook(
        WebhookPayload(
            base_token=settings.feishu_base_token,
            table_id=settings.feishu_table_id,
            record_id="rec1",
            changed_fields=[ARXIV_FIELD],
            secret=settings.webhook_shared_secret,
        )
    )

    assert result.status == "queued"
    assert feishu.updates[0][STATUS_FIELD] == "排队中"

    job = service.claim_next_job()
    assert job is not None
    assert job.trigger_mode == TRIGGER_MODE_WEBHOOK
    assert job.force_rerun is False

    processor = JobProcessor(session, settings, feishu, FakeAnalyzer())
    processor.source_loader.load = lambda selection, title_hint=None: PaperDocument(
        title="Test Paper",
        source_type="arxiv",
        source_hash=selection.source_hash,
        paper_id=selection.paper_id,
        content="abstract\nmethod\nresult",
        sections=[],
        metadata={},
    )
    processor.process(job)

    session.refresh(job)
    assert job.status == "completed"
    assert OUTPUT_ABSTRACT_TRANSLATION in feishu.updates[-1]
    assert feishu.updates[-1][STATUS_FIELD] == STATUS_COMPLETED
    session.close()


def test_job_service_ignores_duplicate_completed_job(test_env):
    settings = get_settings()
    init_database()
    session = get_session_factory()()
    feishu = FakeFeishuClient(settings)
    session.add(
        AnalysisJob(
            base_token=settings.feishu_base_token,
            table_id=settings.feishu_table_id,
            record_id="rec1",
            source_hash="arxiv:2401.01234",
            status="completed",
            attempts=1,
            error=None,
            source_type="arxiv",
            source_meta_json='{"source_type":"arxiv","source_hash":"arxiv:2401.01234","paper_id":"2401.01234","arxiv_id":"2401.01234"}',
            result_json="{}",
            requested_at=utcnow(),
            started_at=utcnow(),
            finished_at=utcnow(),
        )
    )
    session.commit()
    feishu.record_fields["来源哈希"] = "arxiv:2401.01234"
    feishu.record_fields["分析状态"] = "已完成"

    service = JobService(session, settings, feishu)
    result = service.handle_webhook(
        WebhookPayload(
            base_token=settings.feishu_base_token,
            table_id=settings.feishu_table_id,
            record_id="rec1",
            changed_fields=[ARXIV_FIELD],
            secret=settings.webhook_shared_secret,
        )
    )

    assert result.status == "skipped"
    session.close()


def test_local_polling_scanner_enqueues_pending_record_and_marks_force_rerun(test_env):
    settings = get_settings()
    settings.run_mode = "local_polling"
    init_database()
    session = get_session_factory()()
    feishu = FakeFeishuClient(settings)
    feishu.record_fields[STATUS_FIELD] = STATUS_PENDING
    feishu.records = [{"record_id": "rec1", "fields": feishu.record_fields}]

    scanner = LocalPollingScanner(session, settings, feishu)
    results = scanner.scan()

    assert len(results) == 1
    assert results[0].status == "queued"
    job = session.query(AnalysisJob).one()
    assert job.trigger_mode == TRIGGER_MODE_LOCAL_POLLING
    assert job.force_rerun is True
    assert feishu.updates[-1][STATUS_FIELD] == "排队中"
    session.close()


def test_local_polling_scanner_skips_non_pending_records(test_env):
    settings = get_settings()
    settings.run_mode = "local_polling"
    init_database()
    session = get_session_factory()()
    feishu = FakeFeishuClient(settings)
    feishu.record_fields[STATUS_FIELD] = STATUS_COMPLETED
    feishu.records = [{"record_id": "rec1", "fields": feishu.record_fields}]

    scanner = LocalPollingScanner(session, settings, feishu)
    results = scanner.scan()

    assert results == []
    assert session.query(AnalysisJob).count() == 0
    session.close()


def test_local_polling_force_rerun_allows_same_source_hash_after_completion(test_env):
    settings = get_settings()
    settings.run_mode = "local_polling"
    init_database()
    session = get_session_factory()()
    feishu = FakeFeishuClient(settings)
    feishu.record_fields[STATUS_FIELD] = STATUS_PENDING
    feishu.record_fields["来源哈希"] = "arxiv:2401.01234"
    session.add(
        AnalysisJob(
            base_token=settings.feishu_base_token,
            table_id=settings.feishu_table_id,
            record_id="rec1",
            source_hash="arxiv:2401.01234",
            status="completed",
            attempts=1,
            error=None,
            source_type="arxiv",
            trigger_mode=TRIGGER_MODE_WEBHOOK,
            force_rerun=False,
            source_meta_json='{"source_type":"arxiv","source_hash":"arxiv:2401.01234","paper_id":"2401.01234","arxiv_id":"2401.01234"}',
            result_json="{}",
            requested_at=utcnow(),
            started_at=utcnow(),
            finished_at=utcnow(),
        )
    )
    session.commit()

    scanner = LocalPollingScanner(session, settings, feishu)
    results = scanner.scan()

    assert results[0].status == "queued"
    assert session.query(AnalysisJob).count() == 2
    session.close()


def test_local_polling_skips_when_same_source_is_already_pending(test_env):
    settings = get_settings()
    settings.run_mode = "local_polling"
    init_database()
    session = get_session_factory()()
    feishu = FakeFeishuClient(settings)
    feishu.record_fields[STATUS_FIELD] = STATUS_PENDING
    session.add(
        AnalysisJob(
            base_token=settings.feishu_base_token,
            table_id=settings.feishu_table_id,
            record_id="rec1",
            source_hash="arxiv:2401.01234",
            status="queued",
            attempts=0,
            error=None,
            source_type="arxiv",
            trigger_mode=TRIGGER_MODE_LOCAL_POLLING,
            force_rerun=True,
            source_meta_json='{"source_type":"arxiv","source_hash":"arxiv:2401.01234","paper_id":"2401.01234","arxiv_id":"2401.01234"}',
            result_json=None,
            requested_at=utcnow(),
            started_at=None,
            finished_at=None,
        )
    )
    session.commit()

    scanner = LocalPollingScanner(session, settings, feishu)
    results = scanner.scan()

    assert results[0].status == "duplicate"
    assert session.query(AnalysisJob).count() == 1
    session.close()


def test_claim_next_job_is_atomic_and_marks_running(test_env):
    settings = get_settings()
    init_database()
    session = get_session_factory()()
    feishu = FakeFeishuClient(settings)
    session.add(
        AnalysisJob(
            base_token=settings.feishu_base_token,
            table_id=settings.feishu_table_id,
            record_id="rec1",
            source_hash="arxiv:2401.01234",
            status="queued",
            attempts=0,
            error=None,
            source_type="arxiv",
            trigger_mode=TRIGGER_MODE_LOCAL_POLLING,
            force_rerun=True,
            source_meta_json='{"source_type":"arxiv","source_hash":"arxiv:2401.01234","paper_id":"2401.01234","arxiv_id":"2401.01234"}',
            result_json=None,
            requested_at=utcnow(),
            started_at=None,
            finished_at=None,
        )
    )
    session.commit()

    service = JobService(session, settings, feishu)
    claimed = service.claim_next_job()

    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.attempts == 1
    assert claimed.started_at is not None
    session.close()
