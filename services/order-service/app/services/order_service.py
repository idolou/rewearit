"""Order domain service orchestrating atomic garment reservations, escrow locking, and lifecycle events."""
import uuid
from datetime import UTC, datetime

from opentelemetry import trace
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, desc, select

from app.clients.catalog_client import CatalogGrpcClient
from app.core.logging import logger
from app.events.producer import OrderEventProducer
from app.models.order import (
    Order,
    OrderCreateRequest,
    OrderStatus,
)
from app.services.idempotency import IdempotencyManager

tracer = trace.get_tracer("rewearit-order-service")


class OrderServiceError(Exception):
    """Base order service exception."""


class ItemReservationError(OrderServiceError):
    """Raised when garment cannot be reserved via catalog gRPC."""


class PriceMismatchError(OrderServiceError):
    """Raised when client-submitted checkout amount does not match catalog price."""


class SelfPurchaseError(OrderServiceError):
    """Raised when a seller attempts to purchase their own listing."""


class OrderForbiddenError(OrderServiceError):
    """Raised when the authenticated user is not permitted to access or modify an order."""


class OrderNotFoundError(OrderServiceError):
    """Raised when order cannot be found."""


class InvalidStateTransitionError(OrderServiceError):
    """Raised when an order lifecycle transition is invalid."""


class DuplicateProcessingError(OrderServiceError):
    """Raised when an idempotency lock is actively held by a concurrent request."""


class OrderService:
    def __init__(
        self,
        catalog_client: CatalogGrpcClient | None = None,
        idempotency_mgr: IdempotencyManager | None = None,
        producer: OrderEventProducer | None = None,
    ) -> None:
        self.catalog_client = catalog_client or CatalogGrpcClient()
        self.idempotency_mgr = idempotency_mgr or IdempotencyManager()
        self.producer = producer

    async def create_order(
        self,
        session: AsyncSession,
        req: OrderCreateRequest,
        idempotency_key: str,
        buyer_id: uuid.UUID | None = None,
    ) -> Order:
        """Create order with atomic gRPC garment reservation and Redis idempotency."""
        effective_buyer_id = buyer_id or req.buyer_id
        if effective_buyer_id is None:
            raise OrderServiceError("Authenticated buyer_id is required")

        with tracer.start_as_current_span("order_service.create_order") as span:
            span.set_attribute("item.id", str(req.item_id))
            span.set_attribute("buyer.id", str(effective_buyer_id))
            span.set_attribute("idempotency_key", idempotency_key)

            # 1. Acquire atomic in-flight idempotency lock
            acquired = await self.idempotency_mgr.acquire_lock(idempotency_key)
            if not acquired:
                result = await session.execute(
                    select(Order).where(Order.idempotency_key == idempotency_key)
                )
                existing = result.scalar_one_or_none()
                if existing:
                    if existing.buyer_id != effective_buyer_id:
                        raise OrderForbiddenError("Idempotency key belongs to another user")
                    return existing
                raise DuplicateProcessingError("Order checkout is currently in progress for this idempotency key")

            try:
                # Check DB safeguard for previously completed order with this idempotency key
                result = await session.execute(
                    select(Order).where(Order.idempotency_key == idempotency_key)
                )
                existing = result.scalar_one_or_none()
                if existing:
                    if existing.buyer_id != effective_buyer_id:
                        raise OrderForbiddenError("Idempotency key belongs to another user")
                    return existing

                order_id = uuid.uuid4()

                # 2. Atomically reserve item in catalog service via gRPC
                reservation = await self.catalog_client.reserve_item(
                    item_id=req.item_id,
                    order_id=order_id,
                    buyer_id=effective_buyer_id,
                )

                if not reservation.success:
                    logger.warning(
                        f"Reservation rejected by catalog for item_id={req.item_id}: {reservation.error_message}"
                    )
                    raise ItemReservationError(
                        reservation.error_message or "Item is not available for purchase or already reserved"
                    )

                # 3. Fetch authoritative price & seller while holding the reservation
                catalog_item = await self.catalog_client.get_item(req.item_id)
                if catalog_item is None:
                    await self.catalog_client.release_item(req.item_id, order_id, reason="catalog_lookup_failed")
                    raise ItemReservationError("Could not verify item price from catalog")

                if catalog_item.seller_id == effective_buyer_id:
                    await self.catalog_client.release_item(req.item_id, order_id, reason="self_purchase_blocked")
                    raise SelfPurchaseError("You cannot purchase your own listing")

                if (
                    req.total_amount_units != catalog_item.price_units
                    or req.total_amount_nanos != catalog_item.price_nanos
                    or req.currency != catalog_item.currency
                ):
                    await self.catalog_client.release_item(req.item_id, order_id, reason="price_mismatch")
                    raise PriceMismatchError(
                        f"Checkout amount ({req.total_amount_units} {req.currency}) does not match "
                        f"catalog price ({catalog_item.price_units} {catalog_item.currency})"
                    )

                # 4. Create Order record in ESCROW_HELD state using authoritative catalog seller & price
                now = datetime.now(UTC)
                order = Order(
                    id=order_id,
                    buyer_id=effective_buyer_id,
                    seller_id=catalog_item.seller_id,
                    item_id=req.item_id,
                    status=OrderStatus.ESCROW_HELD,
                    total_amount_units=catalog_item.price_units,
                    total_amount_nanos=catalog_item.price_nanos,
                    currency=catalog_item.currency,
                    idempotency_key=idempotency_key,
                    created_at=now,
                    updated_at=now,
                    escrow_locked_at=now,
                )

                try:
                    session.add(order)
                    await session.commit()
                    await session.refresh(order)
                except Exception as e:
                    logger.error(f"Failed to persist order: {e}", exc_info=True)
                    await self.catalog_client.release_item(req.item_id, order_id, reason="order_persistence_failed")
                    raise

                # 5. Publish Kafka events
                if self.producer:
                    try:
                        await self.producer.publish_order_placed(order)
                        await self.producer.publish_order_escrow_locked(order)
                    except Exception as e:
                        logger.error(f"Failed to publish Kafka order events: {e}", exc_info=True)

                logger.info(f"Order created successfully: order_id={order.id}, status={order.status}")
                return order
            finally:
                await self.idempotency_mgr.release_lock(idempotency_key)

    async def get_order(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
        for_update: bool = False,
        actor_id: uuid.UUID | None = None,
    ) -> Order:
        """Fetch order by ID, optionally locking the row and checking participant ownership."""
        query = select(Order).where(Order.id == order_id)
        if for_update:
            query = query.with_for_update()
        result = await session.execute(query)
        order = result.scalar_one_or_none()
        if not order:
            raise OrderNotFoundError(f"Order {order_id} not found")
        if actor_id is not None and actor_id not in (order.buyer_id, order.seller_id):
            raise OrderForbiddenError("You do not have access to this order")
        return order

    async def list_orders(
        self,
        session: AsyncSession,
        buyer_id: uuid.UUID | None = None,
        seller_id: uuid.UUID | None = None,
        participant_id: uuid.UUID | None = None,
        status: OrderStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Order]:
        """Query orders with optional filters."""
        query = select(Order)
        if participant_id is not None:
            query = query.where(or_(col(Order.buyer_id) == participant_id, col(Order.seller_id) == participant_id))
        if buyer_id:
            query = query.where(Order.buyer_id == buyer_id)
        if seller_id:
            query = query.where(Order.seller_id == seller_id)
        if status:
            query = query.where(Order.status == status)

        query = query.order_by(desc(col(Order.created_at))).limit(limit).offset(offset)
        result = await session.execute(query)
        return list(result.scalars().all())

    async def ship_order(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
        tracking_number: str,
        seller_id: uuid.UUID | None = None,
    ) -> Order:
        """Mark order as SHIPPED with tracking number (seller only)."""
        order = await self.get_order(session, order_id, for_update=True)
        if seller_id is not None and order.seller_id != seller_id:
            raise OrderForbiddenError("Only the seller can mark this order as shipped")
        if order.status != OrderStatus.ESCROW_HELD:
            raise InvalidStateTransitionError(
                f"Cannot ship order in status {order.status}; must be in {OrderStatus.ESCROW_HELD}"
            )

        order.status = OrderStatus.SHIPPED
        order.tracking_number = tracking_number
        order.updated_at = datetime.now(UTC)

        session.add(order)
        await session.commit()
        await session.refresh(order)
        logger.info(f"Order {order_id} marked as SHIPPED with tracking={tracking_number}")
        return order

    async def complete_order(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
        buyer_id: uuid.UUID | None = None,
    ) -> Order:
        """Complete order, mark garment SOLD via gRPC, and release escrow funds (buyer only)."""
        order = await self.get_order(session, order_id, for_update=True)
        if buyer_id is not None and order.buyer_id != buyer_id:
            raise OrderForbiddenError("Only the buyer can confirm delivery and release escrow")
        valid_preceding = (OrderStatus.ESCROW_HELD, OrderStatus.SHIPPED, OrderStatus.DELIVERED)
        if order.status not in valid_preceding:
            raise InvalidStateTransitionError(
                f"Cannot complete order in status {order.status}; must be in one of {[s.value for s in valid_preceding]}"
            )

        now = datetime.now(UTC)
        order.status = OrderStatus.COMPLETED
        order.completed_at = now
        order.updated_at = now

        session.add(order)
        await session.commit()
        await session.refresh(order)

        # Synchronously mark SOLD in catalog so a Kafka hiccup cannot let the reservation TTL expire
        await self.catalog_client.mark_item_sold(order.item_id, order.id, order.buyer_id)

        if self.producer:
            try:
                await self.producer.publish_order_completed(order)
            except Exception as e:
                logger.error(f"Failed to publish order.completed event: {e}", exc_info=True)

        logger.info(f"Order {order_id} marked as COMPLETED. Escrow released.")
        return order

    async def cancel_order(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
        reason: str,
        actor_id: uuid.UUID | None = None,
    ) -> Order:
        """Cancel order, refund buyer, and release garment reservation (buyer or seller only)."""
        order = await self.get_order(session, order_id, for_update=True, actor_id=actor_id)
        if order.status in (OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REFUNDED):
            raise InvalidStateTransitionError(
                f"Cannot cancel order in final status {order.status}"
            )

        # Release item reservation in catalog service
        await self.catalog_client.release_item(order.item_id, order.id, reason=reason)

        now = datetime.now(UTC)
        order.status = OrderStatus.CANCELLED
        order.cancellation_reason = reason
        order.cancelled_at = now
        order.updated_at = now

        session.add(order)
        await session.commit()
        await session.refresh(order)

        if self.producer:
            try:
                await self.producer.publish_order_cancelled(order, reason=reason)
            except Exception as e:
                logger.error(f"Failed to publish order.cancelled event: {e}", exc_info=True)

        logger.info(f"Order {order_id} marked as CANCELLED. Garment released.")
        return order
