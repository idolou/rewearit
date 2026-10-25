"""FastAPI probe and monitoring server for rewearit-ai-worker."""
import base64
import uuid
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.pipeline.classifier import (
    AutoFillAttributes,
    GarmentClassifier,
    PriceRangeRecommendation,
)
from app.pipeline.embeddings.encoder import VisualEmbeddingEncoder
from app.pipeline.preprocessor import ImagePreprocessor
from app.storage.s3 import S3Storage

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB
BLOCKED_HOSTS = {"169.254.169.254", "metadata.google.internal"}

app = FastAPI(
    title="ReWearIt AI Worker Probes and Classification Service",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)

# Global status flags tracked by the worker runtime
_is_ready = False
_is_healthy = True

_classifier = GarmentClassifier()
_s3_storage = S3Storage()
_preprocessor = ImagePreprocessor()
_encoder = VisualEmbeddingEncoder(dimension=512)


class ClassifyResponse(BaseModel):
    clean_image_url: str = Field(description="URL of studio enhanced background-removed image")
    original_image_url: str = Field(description="URL of uploaded raw image")
    auto_fill: AutoFillAttributes
    suggested_price_range: PriceRangeRecommendation


class EmbeddingResponse(BaseModel):
    embedding: list[float] = Field(description="512-dimensional normalized embedding vector")
    dimension: int = Field(default=512)


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


@app.post("/api/v1/classify", response_model=ClassifyResponse)
async def classify_item(request: Request) -> ClassifyResponse:
    """Analyze garment photo, isolate foreground on clean studio canvas, and auto-fill metadata."""
    content_type = request.headers.get("content-type", "")
    image_bytes: bytes | None = None
    title = ""
    description = ""
    declared_condition = None

    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        if upload and hasattr(upload, "read"):
            image_bytes = await upload.read()
        title = str(form.get("title", "")) if form.get("title") else ""
        description = str(form.get("description", "")) if form.get("description") else ""
        declared_condition = str(form.get("declared_condition")) if form.get("declared_condition") else None
    else:
        try:
            body = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid request body") from e

        title = body.get("title", "")
        description = body.get("description", "")
        declared_condition = body.get("declared_condition")

        if body.get("image_base64"):
            try:
                image_bytes = base64.b64decode(body["image_base64"])
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid base64 image data: {e}") from e
        elif body.get("image_url"):
            target_url = str(body["image_url"]).strip()
            parsed = urlparse(target_url)
            if parsed.hostname in BLOCKED_HOSTS:
                raise HTTPException(status_code=400, detail="Access to specified host is forbidden")
            try:
                image_bytes = await _preprocessor.fetch_image(target_url)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to fetch image from URL: {e}") from e

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Image must be provided via multipart 'file', 'image_base64', or 'image_url'")

    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Uploaded image exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB size limit")

    session_id = uuid.uuid4().hex[:10]

    # 1. Save original raw image
    orig_key = f"garments/raw/{session_id}.jpg"
    original_url = _s3_storage.upload_bytes(image_bytes, filename=orig_key, content_type="image/jpeg")

    # 2. Run studio enhancement and classifier
    hints = {
        "title": title,
        "description": description,
        "declared_condition": declared_condition,
    }
    result = await _classifier.classify_and_enhance(image_bytes=image_bytes, hints=hints)

    # 3. Save clean catalog image
    clean_key = f"garments/clean/{session_id}.jpg"
    clean_url = _s3_storage.upload_bytes(result.clean_image_bytes, filename=clean_key, content_type="image/jpeg")

    return ClassifyResponse(
        clean_image_url=clean_url,
        original_image_url=original_url,
        auto_fill=result.auto_fill,
        suggested_price_range=result.suggested_price_range,
    )


@app.post("/api/v1/embeddings", response_model=EmbeddingResponse)
async def generate_embedding(request: Request) -> EmbeddingResponse:
    """Generate 512-dimensional multimodal visual embedding from garment photo."""
    content_type = request.headers.get("content-type", "")
    image_bytes: bytes | None = None
    context_text = ""

    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        if upload and hasattr(upload, "read"):
            image_bytes = await upload.read()
        context_text = str(form.get("context_text", "")) if form.get("context_text") else ""
    else:
        try:
            body = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid request body") from e

        context_text = body.get("context_text", "")
        if body.get("image_base64"):
            try:
                image_bytes = base64.b64decode(body["image_base64"])
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid base64 image data: {e}") from e
        elif body.get("image_url"):
            target_url = str(body["image_url"]).strip()
            parsed = urlparse(target_url)
            if parsed.hostname in BLOCKED_HOSTS:
                raise HTTPException(status_code=400, detail="Access to specified host is forbidden")
            try:
                image_bytes = await _preprocessor.fetch_image(target_url)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to fetch image from URL: {e}") from e

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Image must be provided via multipart 'file', 'image_base64', or 'image_url'")

    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Uploaded image exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB size limit")

    embedding = _encoder.encode_image(image_bytes, context_text=context_text)
    return EmbeddingResponse(embedding=embedding, dimension=len(embedding))

