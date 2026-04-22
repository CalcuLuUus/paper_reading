"""HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from paper_analyzer.clients.feishu import FeishuClient
from paper_analyzer.config import Settings, get_settings
from paper_analyzer.database import get_session
from paper_analyzer.schemas import WebhookPayload
from paper_analyzer.services.jobs import JobService

router = APIRouter()


def get_db_session() -> Session:
    yield from get_session()


def get_runtime_settings() -> Settings:
    return get_settings()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/webhooks/feishu/bitable-record", status_code=202)
def handle_feishu_webhook(
    payload: WebhookPayload,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, object]:
    if payload.secret != settings.webhook_shared_secret:
        raise HTTPException(status_code=401, detail="invalid secret")

    service = JobService(session, settings, FeishuClient(settings))
    try:
        result = service.handle_webhook(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.as_dict()

