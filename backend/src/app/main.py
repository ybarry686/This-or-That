import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import get_settings
from app.db import SessionLocal
from app.errors import AppError
from app.realtime.routes import router as realtime_router
from app.rooms.cleanup import cleanup_rooms
from app.rooms.routes import router as rooms_router
from app.tournament.routes import router as tournament_router
from app.tournament.timers import recover_deadlines

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: str


CLEANUP_INTERVAL_SECONDS = 3600


def _run_cleanup() -> None:
    with SessionLocal() as session:
        cleanup_rooms(session, datetime.now(UTC))


async def _cleanup_forever() -> None:
    while True:
        try:
            await run_in_threadpool(_run_cleanup)
        except Exception:
            logger.exception("Room cleanup failed; retrying next interval.")
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await recover_deadlines()
    cleanup = asyncio.create_task(_cleanup_forever())
    yield
    cleanup.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="This or That API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    def handle_app_error(_: Request, error: AppError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail})

    app.include_router(rooms_router)
    app.include_router(tournament_router)
    app.include_router(realtime_router)

    @app.get("/health", response_model=HealthResponse, operation_id="getHealth")
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return app


app = create_app()
