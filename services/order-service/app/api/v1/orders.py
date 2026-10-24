"""FastAPI router for Order management, checkout transactions, and state transitions."""
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.catalog_client import CatalogGrpcClient
from app.core.database import get_session
from app.events.producer import OrderEventProducer
from app.models.order import (
    OrderCancelRequest,
    OrderCreateRequest,
    OrderResponse,
    OrderShipRequest,
    OrderStatus,
)
from app.services.idempotency import IdempotencyManager
from app.services.order_service import (
    DuplicateProcessingError,
    InvalidStateTransitionError,
    ItemReservationError,
    OrderNotFoundError,
    OrderService,
)

router = APIRouter(prefix="/orders", tags=["Orders"])

# Global shared service components (initialized on lifespan)
_order_service: OrderService | None = None


def set_order_service(service: OrderService) -> None:
    global _order_service
    _order_service = service


def get_order_service() -> OrderService:
    global _order_service
    if _order_service is None:
        _order_service = OrderService(
            catalog_client=CatalogGrpcClient(),
            idempotency_mgr=IdempotencyManager(),
            producer=OrderEventProducer(),
        )
    return _order_service


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create order with atomic 1-of-1 garment reservation and idempotency",
)
async def create_order(
    req: OrderCreateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", description="Unique idempotency transaction key"),
    session: AsyncSession = Depends(get_session),
    order_service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is mandatory and cannot be empty",
        )

    try:
        order = await order_service.create_order(session, req, idempotency_key.strip())
        return OrderResponse.model_validate(order, from_attributes=True)
    except ItemReservationError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Item reservation rejected: {e}",
        ) from e
    except DuplicateProcessingError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Retrieve order details by ID",
)
async def get_order(
    order_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    order_service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    try:
        order = await order_service.get_order(session, order_id)
        return OrderResponse.model_validate(order, from_attributes=True)
    except OrderNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found",
        ) from e


@router.get(
    "",
    response_model=list[OrderResponse],
    summary="List orders with optional filtering",
)
async def list_orders(
    buyer_id: uuid.UUID | None = Query(None, description="Filter by buyer UUID"),
    seller_id: uuid.UUID | None = Query(None, description="Filter by seller UUID"),
    order_status: OrderStatus | None = Query(None, alias="status", description="Filter by order status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    order_service: OrderService = Depends(get_order_service),
) -> list[OrderResponse]:
    orders = await order_service.list_orders(
        session=session,
        buyer_id=buyer_id,
        seller_id=seller_id,
        status=order_status,
        limit=limit,
        offset=offset,
    )
    return [OrderResponse.model_validate(o, from_attributes=True) for o in orders]


@router.post(
    "/{order_id}/ship",
    response_model=OrderResponse,
    summary="Mark order as SHIPPED with tracking number",
)
async def ship_order(
    order_id: uuid.UUID,
    req: OrderShipRequest,
    session: AsyncSession = Depends(get_session),
    order_service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    try:
        order = await order_service.ship_order(session, order_id, req.tracking_number)
        return OrderResponse.model_validate(order, from_attributes=True)
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order {order_id} not found") from e
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/{order_id}/complete",
    response_model=OrderResponse,
    summary="Complete order, release escrow funds, and trigger garment sold event",
)
async def complete_order(
    order_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    order_service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    try:
        order = await order_service.complete_order(session, order_id)
        return OrderResponse.model_validate(order, from_attributes=True)
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order {order_id} not found") from e
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/{order_id}/cancel",
    response_model=OrderResponse,
    summary="Cancel order, refund buyer, and release garment reservation",
)
async def cancel_order(
    order_id: uuid.UUID,
    req: OrderCancelRequest,
    session: AsyncSession = Depends(get_session),
    order_service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    try:
        order = await order_service.cancel_order(session, order_id, reason=req.reason)
        return OrderResponse.model_validate(order, from_attributes=True)
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order {order_id} not found") from e
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
