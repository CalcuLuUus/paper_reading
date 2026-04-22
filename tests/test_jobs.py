from paper_analyzer.clients.feishu import FeishuClient
from paper_analyzer.clients.llm import OpenAICompatibleClient
from paper_analyzer.config import get_settings
from paper_analyzer.constants import (
    ARXIV_FIELD,
    ERROR_FIELD,
    OUTPUT_ABSTRACT_TRANSLATION,
    STATUS_COMPLETED,
    STATUS_FIELD,
)
from paper_analyzer.database import get_session_factory, init_database
from paper_analyzer.models import AnalysisJob
from paper_analyzer.schemas import PaperAnalysisOutput, PaperDocument, WebhookPayload
from paper_analyzer.services.analysis import PaperAnalyzer
from paper_analyzer.services.jobs import JobProcessor, JobService
from paper_analyzer.utils import utcnow


class FakeFeishuClient(FeishuClient):
    def __init__(self, settings):
        super().__init__(settings)
        self.updates = []
        self.record_fields = {
            "论文标题/备注": "Test Paper",
            ARXIV_FIELD: "https://arxiv.org/abs/2401.01234",
        }

    def get_tenant_access_token(self):
        return "token"

    def get_record(self, base_token, table_id, record_id):
        return {"record_id": record_id, "fields": self.record_fields}

    def update_record(self, base_token, table_id, record_id, fields):
        self.updates.append(fields)
        self.record_fields.update(fields)
        return {"record_id": record_id, "fields": self.record_fields}


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

