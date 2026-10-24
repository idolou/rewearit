"""FastAPI application entrypoint for ReWearIt Catalog Service."""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import text

from app.api.v1 import api_v1_router
from app.core.config import settings
from app.core.database import engine, init_db
from app.core.logging import logger, setup_logging
from app.core.telemetry import init_tracer, instrument_app
from app.events.consumer import consumer
from app.events.producer import producer
from app.grpc.server import grpc_server

# Initialize tracer
tracer = init_tracer(settings.SERVICE_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle management."""
    setup_logging()
    logger.info(f"Initializing {settings.SERVICE_NAME} in environment={settings.ENVIRONMENT}...")

    # 1. Database schema initialization
    try:
        await init_db()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)

    # 2. Start Kafka Producer
    try:
        await producer.start()
    except Exception as e:
        logger.warning(f"Could not connect Kafka producer on startup: {e}. Will retry on demand.")

    # 3. Start Kafka Consumer
    try:
        await consumer.start()
    except Exception as e:
        logger.warning(f"Could not connect Kafka consumer on startup: {e}.")

    # 4. Start gRPC Server
    try:
        await grpc_server.start()
    except Exception as e:
        logger.error(f"Failed to start gRPC server: {e}", exc_info=True)

    logger.info(f"{settings.SERVICE_NAME} startup complete. REST={settings.REST_PORT}, gRPC={settings.GRPC_PORT}.")
    yield

    # Shutdown
    logger.info("Shutting down catalog service...")
    await grpc_server.stop()
    await consumer.stop()
    await producer.stop()
    await engine.dispose()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="ReWearIt Catalog Service",
    description="Microservice managing secondhand garment listings, pgvector visual search, and inventory reservation locks",
    version="1.0.0",
    lifespan=lifespan,
)

instrument_app(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/upload", include_in_schema=False)
async def upload_page() -> FileResponse:
    """Interactive seller studio upload and preview page."""
    return FileResponse(STATIC_DIR / "upload_preview.html", media_type="text/html")



@app.get("/healthz", status_code=status.HTTP_200_OK, tags=["Health"])
async def healthz() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "service": settings.SERVICE_NAME}


@app.get("/ready", status_code=status.HTTP_200_OK, tags=["Health"])
async def ready() -> dict[str, str]:
    """Readiness probe checking database connectivity."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {"status": "degraded", "database": str(e)}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.REST_HOST,
        port=settings.REST_PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )
