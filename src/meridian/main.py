"""FastAPI app factory — the Meridian control plane.

Ingests tasks and exposes status/trace. It never runs the agent inline; that is
the arq worker's job. The agent loop runs out-of-band so HTTP stays fast while
tasks run for minutes across 20-40+ tool calls.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI

from meridian.api.routes_tasks import router as tasks_router
from meridian.api.routes_tasks import webhook_router
from meridian.config import get_settings
from meridian.persistence.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    app.state.redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        yield
    finally:
        await app.state.redis.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Meridian", version="0.1.0", lifespan=lifespan)
    app.include_router(tasks_router)
    app.include_router(webhook_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
