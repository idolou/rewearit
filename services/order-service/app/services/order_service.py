"""Order domain service orchestrating atomic garment reservations, escrow locking, and lifecycle events."""
import uuid
from datetime import UTC, datetime

from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, desc, select

from app.clients.catalog_client import CatalogGrpcClient
from app.core.logging import logger
from app.events.producer import OrderEventProducer
from app.models.order import (
    Order,
    OrderCreateRequest,
    OrderResponse,
    OrderStatus,
)
from app.services.idempotency import IdempotencyManager

tracer = trace.get_tracer("rewearit-order-service")


class OrderServiceError(Exception):
    """Base order service exception."""


class ItemReservationError(OrderServiceError):
    """Raised when garment cannot be reserved via catalog gRPC."""


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
    ) -> Order:
        """Create order with atomic gRPC garment reservation and Redis idempotency."""
        with tracer.start_as_current_span("order_service.create_order") as span:
            span.set_attribute("item.id", str(req.item_id))
            span.set_attribute("buyer.id", str(req.buyer_id))
            span.set_attribute("idempotency_key", idempotency_key)

            # 1. Acquire atomic idempotency lock
            acquired = await self.idempotency_mgr.acquire_lock(idempotency_key)
            if not acquired:
                # Check if already processed and stored
                cached = await self.idempotency_mgr.get_cached_response(idempotency_key)
                if cached:
                    logger.info(f"Returning cached order for idempotency_key={idempotency_key}")
                    # Look up from database to return model
                    result = await session.execute(
                        select(Order).where(Order.idempotency_key == idempotency_key)
                    )
                    existing = result.scalar_one_or_none()
                    if existing:
                        return existing

                raise DuplicateProcessingError("Order checkout is currently in progress for this idempotency key")

            # Check DB safeguard for existing order with this idempotency key
            result = await session.execute(
                select(Order).where(Order.idempotency_key == idempotency_key)
            )
            existing = result.scalar_one_or_none()
            if existing:
                await self.idempotency_mgr.release_lock(idempotency_key)
                return existing

            order_id = uuid.uuid4()

            # 2. Atomically reserve item in catalog service via gRPC
            reservation = await self.catalog_client.reserve_item(
                item_id=req.item_id,
                order_id=order_id,
                buyer_id=req.buyer_id,
            )

            if not reservation.success:
                logger.warning(
                    f"Reservation rejected by catalog for item_id={req.item_id}: {reservation.error_message}"
                )
                await self.idempotency_mgr.release_lock(idempotency_key)
                raise ItemReservationError(
                    reservation.error_message or "Item is not available for purchase or already reserved"
                )

            # 3. Create Order record in ESCROW_HELD state
            now = datetime.now(UTC)
            order = Order(
                id=order_id,
                buyer_id=req.buyer_id,
                seller_id=req.seller_id,
                item_id=req.item_id,
                status=OrderStatus.ESCROW_HELD,
                total_amount_units=req.total_amount_units,
                total_amount_nanos=req.total_amount_nanos,
                currency=req.currency,
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
                # Compensating transaction: release item reservation in catalog
                await self.catalog_client.release_item(req.item_id, order_id, reason="order_persistence_failed")
                await self.idempotency_mgr.release_lock(idempotency_key)
                raise

            # 4. Publish Kafka events
            if self.producer:
                try:
                    await self.producer.publish_order_placed(order)
                    await self.producer.publish_order_escrow_locked(order)
                except Exception as e:
                    logger.error(f"Failed to publish Kafka order events: {e}", exc_info=True)

            # 5. Store completed response in Redis idempotency cache
            order_dict = OrderResponse.model_validate(order, from_attributes=True).model_dump(mode="json")
            await self.idempotency_mgr.store_response(idempotency_key, order_dict)

            logger.info(f"Order created successfully: order_id={order.id}, status={order.status}")
            return order

    async def get_order(self, session: AsyncSession, order_id: uuid.UUID) -> Order:
        """Fetch order by ID."""
        result = await session.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
        if not order:
            raise OrderNotFoundError(f"Order {order_id} not found")
        return order

    async def list_orders(
        self,
        session: AsyncSession,
        buyer_id: uuid.UUID | None = None,
        seller_id: uuid.UUID | None = None,
        status: OrderStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Order]:
        """Query orders with optional filters."""
        query = select(Order)
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
    ) -> Order:
        """Mark order as SHIPPED with tracking number."""
        order = await self.get_order(session, order_id)
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

    async def complete_order(self, session: AsyncSession, order_id: uuid.UUID) -> Order:
        """Complete order and release escrow funds to seller."""
        order = await self.get_order(session, order_id)
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
    ) -> Order:
        """Cancel order, refund buyer, and release garment reservation via gRPC."""
        order = await self.get_order(session, order_id)
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
