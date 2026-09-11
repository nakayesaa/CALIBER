"""CALIBER API application entry point."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.api.app.api.routes import router
from services.api.app.services.backend import BackendService


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def create_app(
    root: Path = REPOSITORY_ROOT,
    backend: BackendService | None = None,
) -> FastAPI:
    application = FastAPI(
        title="CALIBER Reliability Intelligence API",
        version="0.2.0",
    )
    application.state.backend = backend or BackendService(root)
    origins = [
        origin.strip()
        for origin in os.getenv(
            "CALIBER_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["*"],
    )

    @application.get("/health", tags=["system"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    application.include_router(router)
    return application


app = create_app()
