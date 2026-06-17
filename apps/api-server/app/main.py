from contextlib import asynccontextmanager

from fastapi import FastAPI
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
