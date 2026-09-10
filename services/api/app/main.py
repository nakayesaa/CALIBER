"""CALIBER API application entry point."""

from fastapi import FastAPI


app = FastAPI(
    title="CALIBER Reliability Intelligence API",
    version="0.1.0",
)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Return a dependency-free liveness response."""

    return {"status": "ok"}


@app.get("/api/v1/status", tags=["system"])
def project_status() -> dict[str, str]:
    """Expose the current implementation milestone."""

    return {
        "phase": "ko_3201_vertical_slice",
        "data_status": "not_materialized",
        "api_status": "scaffold",
    }

