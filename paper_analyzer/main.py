"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from paper_analyzer.api.routes import router
from paper_analyzer.config import get_settings
from paper_analyzer.database import init_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


settings = get_settings()
init_database()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(router)
