"""FastAPI router for apparel catalog items and visual search."""
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.models.item import ConditionGrade, Item, ItemBase, ItemStatus
from app.services.catalog_service import CatalogService

router = APIRouter(prefix="/items", tags=["Catalog Items"])


@router.post("/classify")
async def classify_item(request: Request) -> dict[str, Any]:
    """Proxy image upload to ai-worker for studio background removal and auto-fill."""
    content_type = request.headers.get("content-type", "")
    target_url = f"{settings.AI_WORKER_URL}/api/v1/classify"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if "multipart/form-data" in content_type:
                form = await request.form()
                files = {}
                data = {}
                for k, v in form.items():
                    if hasattr(v, "read"):
                        file_bytes = await v.read()
                        if len(file_bytes) > 15 * 1024 * 1024:
                            raise HTTPException(status_code=413, detail="File size exceeds 15MB limit")
                        files[k] = (v.filename or "upload.jpg", file_bytes, v.content_type or "image/jpeg")
                    else:
                        data[k] = str(v)
                resp = await client.post(target_url, files=files, data=data)
            else:
                body = await request.json()
                resp = await client.post(target_url, json=body)

            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]
        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=f"AI Worker error: {e.response.text}") from e
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Could not reach AI Worker at {target_url}: {e}") from e



class VisualSearchRequest(BaseModel):
    embedding: list[float] = Field(..., description="512-dimensional CLIP embedding vector")
    limit: int = Field(default=10, ge=1, le=50)
    max_distance: float = Field(default=0.8, ge=0.0, le=2.0)


class VisualSearchResultItem(BaseModel):
    item: Item
    distance: float
    similarity: float


@router.post("", response_model=Item, status_code=status.HTTP_201_CREATED)
async def create_item(
    item_in: ItemBase,
    session: AsyncSession = Depends(get_session),
    x_correlation_id: str | None = Header(default=None),
) -> Item:
    """Create a new apparel listing and emit an ItemCreatedEvent."""
    return await CatalogService.create_item(session, item_in, correlation_id=x_correlation_id)


@router.get("/{item_id}", response_model=Item)
async def get_item(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Item:
    """Retrieve single item by UUID."""
    item = await CatalogService.get_item_by_id(session, item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id '{item_id}' not found",
        )
    return item


@router.get("", response_model=list[Item])
async def list_items(
    category: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    condition_grade: ConditionGrade | None = Query(default=None),
    status: ItemStatus | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[Item]:
    """List catalog items with optional filtering."""
    return await CatalogService.list_items(
        session=session,
        category=category,
        brand=brand,
        condition_grade=condition_grade,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.post("/search/visual", response_model=list[VisualSearchResultItem])
async def visual_search(
    request: VisualSearchRequest,
    session: AsyncSession = Depends(get_session),
) -> list[VisualSearchResultItem]:
    """Semantic visual similarity search using pgvector cosine distance."""
    if len(request.embedding) != 512:
        raise HTTPException(
            status_code=422,
            detail=f"Embedding must contain exactly 512 float values, got {len(request.embedding)}",
        )

    results = await CatalogService.search_visual(
        session=session,
        embedding=request.embedding,
        limit=request.limit,
        max_distance=request.max_distance,
    )

    return [
        VisualSearchResultItem(
            item=item,
            distance=dist,
            similarity=round(1.0 - (dist / 2.0), 4),
        )
        for item, dist in results
    ]


async def fetch_image_embedding(
    image_bytes: bytes | None = None,
    image_url: str | None = None,
    image_base64: str | None = None,
    context_text: str = "",
) -> list[float]:
    """Retrieve 512-dim visual embedding from ai-worker."""
    target_url = f"{settings.AI_WORKER_URL}/api/v1/embeddings"
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if image_bytes is not None:
                files = {"file": ("query.jpg", image_bytes, "image/jpeg")}
                data = {"context_text": context_text} if context_text else {}
                resp = await client.post(target_url, files=files, data=data)
            else:
                payload: dict[str, Any] = {}
                if image_base64:
                    payload["image_base64"] = image_base64
                elif image_url:
                    payload["image_url"] = image_url
                if context_text:
                    payload["context_text"] = context_text
                resp = await client.post(target_url, json=payload)

            resp.raise_for_status()
            emb_data = resp.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=f"AI Worker error: {e.response.text}") from e
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Could not reach AI Worker at {target_url}: {e}") from e

    embedding = emb_data.get("embedding", [])
    if len(embedding) != 512:
        raise HTTPException(status_code=500, detail="AI Worker returned invalid embedding dimension")
    return embedding  # type: ignore[no-any-return]


@router.post("/search/visual-image", response_model=list[VisualSearchResultItem])
async def visual_image_search(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
    max_distance: float = Query(default=0.8, ge=0.0, le=2.0),
    session: AsyncSession = Depends(get_session),
) -> list[VisualSearchResultItem]:
    """Semantic visual similarity search directly from uploaded query photo or image URL."""
    content_type = request.headers.get("content-type", "")
    image_bytes: bytes | None = None
    image_url: str | None = None
    image_base64: str | None = None
    context_text = ""

    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        if upload and hasattr(upload, "read"):
            image_bytes = await upload.read()
            if len(image_bytes) > 15 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="File size exceeds 15MB limit")
        context_text = str(form.get("context_text", "")) if form.get("context_text") else ""
    else:
        try:
            body = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid request body") from e
        image_url = body.get("image_url")
        image_base64 = body.get("image_base64")
        context_text = body.get("context_text", "")

    if not image_bytes and not image_url and not image_base64:
        raise HTTPException(status_code=400, detail="Query image must be provided via 'file', 'image_url', or 'image_base64'")

    embedding = await fetch_image_embedding(
        image_bytes=image_bytes,
        image_url=image_url,
        image_base64=image_base64,
        context_text=context_text,
    )

    results = await CatalogService.search_visual(
        session=session,
        embedding=embedding,
        limit=limit,
        max_distance=max_distance,
    )

    return [
        VisualSearchResultItem(
            item=item,
            distance=dist,
            similarity=round(1.0 - (dist / 2.0), 4),
        )
        for item, dist in results
    ]

