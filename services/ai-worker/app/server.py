"""FastAPI probe and monitoring server for rewearit-ai-worker."""
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core.config import settings

app = FastAPI(
    title="ReWearIt AI Worker Probes",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
)

# Global status flags tracked by the worker runtime
_is_ready = False
_is_healthy = True


def set_ready(ready: bool) -> None:
    global _is_ready
    _is_ready = ready


def set_healthy(healthy: bool) -> None:
    global _is_healthy
    _is_healthy = healthy


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    if not _is_healthy:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "service": settings.SERVICE_NAME})  # type: ignore[return-value]
    return {"status": "ok", "service": settings.SERVICE_NAME}


@app.get("/ready")
async def ready() -> dict[str, Any]:
    if not _is_ready:
        return JSONResponse(status_code=503, content={"status": "not_ready", "service": settings.SERVICE_NAME})  # type: ignore[return-value]
    return {"status": "ready", "service": settings.SERVICE_NAME}
