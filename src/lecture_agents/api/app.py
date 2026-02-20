"""
FastAPI application factory for the Lecture-to-Notes Pipeline API.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # Load .env (ANTHROPIC_API_KEY, etc.) before anything else

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from lecture_agents.api.job_manager import JobManager
from lecture_agents.api.routes import router

job_manager = JobManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    job_manager.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Lecture-to-Notes Pipeline API",
        description=(
            "REST API for transforming audio lectures into "
            "enriched, structured Markdown and PDF notes."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:5174",
            "http://localhost:5175",
            "http://localhost:5176",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.job_manager = job_manager
    app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
