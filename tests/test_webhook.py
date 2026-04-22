import importlib

from fastapi.testclient import TestClient

import paper_analyzer.main
from paper_analyzer.config import get_settings
from paper_analyzer.constants import ARXIV_FIELD
from paper_analyzer.database import get_engine, get_session_factory
from paper_analyzer.models import AnalysisJob


class DummyFeishuClient:
    def __init__(self, settings):
        self.settings = settings

    def get_record(self, base_token, table_id, record_id):
        return {
            "record_id": record_id,
            "fields": {
                "论文标题/备注": "Paper",
                ARXIV_FIELD: "https://arxiv.org/abs/2401.01234",
            },
        }

    def update_record(self, base_token, table_id, record_id, fields):
        return {"record_id": record_id, "fields": fields}


def test_webhook_rejects_invalid_secret(test_env, monkeypatch):
    importlib.reload(paper_analyzer.main)
    client = TestClient(paper_analyzer.main.app)

    response = client.post(
        "/webhooks/feishu/bitable-record",
        json={
            "base_token": get_settings().feishu_base_token,
            "table_id": get_settings().feishu_table_id,
            "record_id": "rec1",
            "changed_fields": [ARXIV_FIELD],
            "secret": "wrong",
        },
    )

    assert response.status_code == 401


def test_webhook_ignores_non_trigger_fields(test_env, monkeypatch):
    import paper_analyzer.api.routes as routes

    monkeypatch.setattr(routes, "FeishuClient", DummyFeishuClient)
    importlib.reload(paper_analyzer.main)
    client = TestClient(paper_analyzer.main.app)

    response = client.post(
        "/webhooks/feishu/bitable-record",
        json={
            "base_token": get_settings().feishu_base_token,
            "table_id": get_settings().feishu_table_id,
            "record_id": "rec1",
            "changed_fields": ["分析状态"],
            "secret": get_settings().webhook_shared_secret,
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "ignored"


def test_webhook_queues_job(test_env, monkeypatch):
    import paper_analyzer.api.routes as routes

    monkeypatch.setattr(routes, "FeishuClient", DummyFeishuClient)
    importlib.reload(paper_analyzer.main)
    client = TestClient(paper_analyzer.main.app)

    response = client.post(
        "/webhooks/feishu/bitable-record",
        json={
            "base_token": get_settings().feishu_base_token,
            "table_id": get_settings().feishu_table_id,
            "record_id": "rec1",
            "changed_fields": [ARXIV_FIELD],
            "secret": get_settings().webhook_shared_secret,
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"

    session = get_session_factory()()
    job = session.query(AnalysisJob).one()
    assert job.record_id == "rec1"
    session.close()

