import logging
from time import perf_counter
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    assets,
    core3_mvp,
    core3_real_data,
    export,
    files,
    goal1,
    goal2,
    health,
    imports,
    pipeline,
    profiling,
    projects,
    workbench,
)
from app.core.config import get_settings
from app.core.database import init_db


logger = logging.getLogger("catforge.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()
    settings.resolved_upload_dir.mkdir(parents=True, exist_ok=True)
    settings.resolved_export_dir.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def log_slow_requests(request: Request, call_next):
        started_at = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed = perf_counter() - started_at
            logger.exception(
                "request failed method=%s path=%s duration=%.3fs",
                request.method,
                request.url.path,
                elapsed,
            )
            raise
        elapsed = perf_counter() - started_at
        if elapsed >= settings.slow_request_seconds:
            logger.warning(
                "slow request method=%s path=%s status=%s duration=%.3fs",
                request.method,
                request.url.path,
                response.status_code,
                elapsed,
            )
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(projects.router)
    app.include_router(files.router)
    app.include_router(imports.router)
    app.include_router(profiling.router)
    app.include_router(pipeline.router)
    app.include_router(goal1.router)
    app.include_router(goal2.router)
    app.include_router(core3_mvp.router)
    app.include_router(core3_real_data.router)
    app.include_router(workbench.router)
    app.include_router(assets.router)
    app.include_router(export.router)
    return app


app = create_app()
