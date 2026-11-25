"""FastAPI application entrypoint for ReWearIt Catalog Service."""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
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
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router)


async def _proxy_orders(request: Request, subpath: str = "") -> Response:
    """Forward authenticated order requests from browser UIs to order-service."""
    headers: dict[str, str] = {}
    if auth := request.headers.get("authorization"):
        headers["Authorization"] = auth
    if idemp := request.headers.get("idempotency-key"):
        headers["Idempotency-Key"] = idemp
    if ctype := request.headers.get("content-type"):
        headers["Content-Type"] = ctype

    query = f"?{request.url.query}" if request.url.query else ""
    target_url = f"{settings.ORDER_SERVICE_URL.rstrip('/')}/api/v1/orders{subpath}{query}"
    body = await request.body() if request.method == "POST" else None

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.request(request.method, target_url, content=body, headers=headers)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Could not reach order service: {e}") from e
    return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")


@app.api_route("/api/v1/orders", methods=["GET", "POST"], include_in_schema=False)
async def proxy_orders_root(request: Request) -> Response:
    return await _proxy_orders(request)


@app.post("/api/v1/orders/{order_id}/{action}", include_in_schema=False)
async def proxy_order_action(order_id: str, action: str, request: Request) -> Response:
    if action not in ("ship", "complete", "cancel"):
        raise HTTPException(status_code=404, detail="Unknown order action")
    return await _proxy_orders(request, subpath=f"/{order_id}/{action}")


STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/", include_in_schema=False)
@app.get("/explore", include_in_schema=False)
async def buyer_catalog_page() -> FileResponse:
    """Buyer marketplace catalog and visual search interface."""
    return FileResponse(STATIC_DIR / "buyer_catalog.html", media_type="text/html")


@app.get("/upload", include_in_schema=False)
async def upload_page() -> FileResponse:
    """Interactive seller studio upload and preview page."""
    return FileResponse(STATIC_DIR / "upload_preview.html", media_type="text/html")


@app.get("/seller", include_in_schema=False)
async def seller_dashboard_page() -> FileResponse:
    """Seller dashboard for managing listings, incoming orders, shipping, and payouts."""
    return FileResponse(STATIC_DIR / "seller_dashboard.html", media_type="text/html")


@app.get("/static/auth.js", include_in_schema=False)
async def auth_script() -> FileResponse:
    """Shared client-side auth modal and token helper for marketplace pages."""
    return FileResponse(STATIC_DIR / "auth.js", media_type="application/javascript")


@app.get("/healthz", status_code=status.HTTP_200_OK, tags=["Health"])
async def healthz() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "service": settings.SERVICE_NAME}


@app.get("/ready", status_code=status.HTTP_200_OK, tags=["Health"], response_model=None)
async def ready() -> dict[str, str] | JSONResponse:
    """Readiness probe checking database connectivity."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "unavailable"})


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.REST_HOST,
        port=settings.REST_PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )
