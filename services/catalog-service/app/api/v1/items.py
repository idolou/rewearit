"""FastAPI router for apparel catalog items and visual search."""
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.item import ConditionGrade, Item, ItemBase, ItemStatus
from app.services.catalog_service import CatalogService

router = APIRouter(prefix="/items", tags=["Catalog Items"])


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
