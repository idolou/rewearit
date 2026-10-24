"""Main entrypoint and FastAPI application for rewearit-order-service."""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.orders import router as orders_router
from app.api.v1.orders import set_order_service
from app.clients.catalog_client import CatalogGrpcClient
from app.core.config import settings
from app.core.database import init_db
from app.core.logging import logger, setup_logging
from app.core.telemetry import init_tracer, instrument_app
from app.events.producer import OrderEventProducer
from app.services.idempotency import IdempotencyManager
from app.services.order_service import OrderService

setup_logging()
init_tracer(settings.SERVICE_NAME)

producer = OrderEventProducer()
idempotency_mgr = IdempotencyManager()
catalog_client = CatalogGrpcClient()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(f"Initializing {settings.SERVICE_NAME} in environment={settings.ENVIRONMENT}...")

    # Ensure database schema is created
    try:
        await init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.warning(f"Database init warning (will retry on queries): {e}")

    # Start Kafka event producer
    try:
        await producer.start()
    except Exception as e:
        logger.warning(f"Could not connect Kafka producer on startup: {e}")

    # Wire up OrderService
    order_service = OrderService(
        catalog_client=catalog_client,
        idempotency_mgr=idempotency_mgr,
        producer=producer,
    )
    set_order_service(order_service)
    logger.info("OrderService wired and ready.")

    yield

    logger.info("Shutting down rewearit-order-service...")
    await producer.stop()
    await idempotency_mgr.close()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="ReWearIt Order & Checkout Service",
    description="Microservice managing transactions, atomic gRPC reservations, escrow state machine, and event streaming",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

instrument_app(app)

app.include_router(orders_router, prefix="/api/v1")


@app.get("/health/live", tags=["Health"])
@app.get("/healthz", tags=["Health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok", "service": settings.SERVICE_NAME}


@app.get("/health/ready", tags=["Health"])
@app.get("/ready", tags=["Health"])
async def readiness() -> dict[str, str]:
    return {"status": "ready", "service": settings.SERVICE_NAME}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.REST_HOST,
        port=settings.REST_PORT,
        log_level=settings.LOG_LEVEL.lower(),
        reload=False,
    )
