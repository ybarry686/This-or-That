from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import get_settings
from app.errors import AppError
from app.realtime.routes import router as realtime_router
from app.rooms.routes import router as rooms_router
from app.tournament.routes import router as tournament_router
from app.tournament.timers import recover_deadlines


class HealthResponse(BaseModel):
    status: str


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await recover_deadlines()
    yield


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
