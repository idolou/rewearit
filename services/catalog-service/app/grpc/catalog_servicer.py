"""gRPC servicer implementing CatalogService with atomic 1-of-1 reservation locks."""
import time
import uuid

import grpc
from sqlalchemy import select

from app.core.database import async_session_maker
from app.core.logging import logger
from app.events.schemas import map_condition_grade_to_proto, map_status_to_proto
from app.grpc.schemas import catalog_service_pb2, catalog_service_pb2_grpc, events_pb2
from app.models.item import Item, ItemStatus


def item_to_proto(item: Item) -> catalog_service_pb2.ItemResponse:
    """Convert domain Item entity to gRPC ItemResponse."""
    price_proto = events_pb2.Money(
        currency=item.price_currency,
        units=item.price_units,
        nanos=item.price_nanos,
    )
    return catalog_service_pb2.ItemResponse(
        item_id=str(item.id),
        seller_id=str(item.seller_id),
        title=item.title,
        description=item.description,
        category=item.category,
        brand=item.brand,
        size=item.size,
        condition_grade=map_condition_grade_to_proto(item.condition_grade),
        price=price_proto,
        status=map_status_to_proto(item.status),
        image_urls=item.image_urls,
        reserved_until_timestamp=item.reserved_until_timestamp or 0,
    )


class CatalogServicer(catalog_service_pb2_grpc.CatalogServiceServicer):
    async def GetItem(
        self,
        request: catalog_service_pb2.GetItemRequest,
        context: grpc.aio.ServicerContext,
    ) -> catalog_service_pb2.ItemResponse:
        """Fetch item details by UUID."""
        try:
            item_uuid = uuid.UUID(request.item_id)
        except ValueError:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"Invalid UUID: {request.item_id}")

        async with async_session_maker() as session:
            result = await session.execute(select(Item).where(Item.id == item_uuid))
            item = result.scalar_one_or_none()
            if not item:
                await context.abort(grpc.StatusCode.NOT_FOUND, f"Item '{request.item_id}' not found")
            return item_to_proto(item)

    async def ReserveItem(
        self,
        request: catalog_service_pb2.ReserveItemRequest,
        context: grpc.aio.ServicerContext,
    ) -> catalog_service_pb2.ReserveItemResponse:
        """Atomically reserve an item using SELECT ... FOR UPDATE."""
        try:
            item_uuid = uuid.UUID(request.item_id)
            order_uuid = uuid.UUID(request.order_id)
        except ValueError as e:
            return catalog_service_pb2.ReserveItemResponse(
                success=False,
                error_message=f"Invalid UUID format: {e}",
            )

        ttl = request.ttl_seconds if request.ttl_seconds > 0 else 900
        now = int(time.time())
        expires_at = now + ttl

        async with async_session_maker() as session:
            async with session.begin():
                # Strict row-level lock
                query = select(Item).where(Item.id == item_uuid).with_for_update()
                result = await session.execute(query)
                item = result.scalar_one_or_none()

                if not item:
                    return catalog_service_pb2.ReserveItemResponse(
                        success=False,
                        error_message=f"Item '{request.item_id}' not found",
                    )

                # Check if already reserved by this same order (idempotent retry)
                if item.status == ItemStatus.RESERVED and item.reserved_by_order_id == order_uuid:
                    logger.info(f"Item {item_uuid} already reserved by order {order_uuid}. Idempotent return.")
                    return catalog_service_pb2.ReserveItemResponse(
                        success=True,
                        expires_at_timestamp=item.reserved_until_timestamp or expires_at,
                    )

                # If reserved by someone else, check if expired
                if item.status == ItemStatus.RESERVED:
                    if item.reserved_until_timestamp and item.reserved_until_timestamp < now:
                        logger.info(f"Item {item_uuid} previous reservation expired. Reclaiming.")
                    else:
                        return catalog_service_pb2.ReserveItemResponse(
                            success=False,
                            error_message="Item is currently reserved by another active order",
                        )
                elif item.status != ItemStatus.ACTIVE:
                    return catalog_service_pb2.ReserveItemResponse(
                        success=False,
                        error_message=f"Item is not available for reservation (status={item.status.value})",
                    )

                # Lock the reservation
                item.status = ItemStatus.RESERVED
                item.reserved_by_order_id = order_uuid
                item.reserved_until_timestamp = expires_at
                session.add(item)

        logger.info(f"Item {item_uuid} reserved successfully for order {order_uuid} until {expires_at}")
        return catalog_service_pb2.ReserveItemResponse(
            success=True,
            expires_at_timestamp=expires_at,
        )

    async def ReleaseItem(
        self,
        request: catalog_service_pb2.ReleaseItemRequest,
        context: grpc.aio.ServicerContext,
    ) -> catalog_service_pb2.ReleaseItemResponse:
        """Release reservation if cancelled or timed out."""
        try:
            item_uuid = uuid.UUID(request.item_id)
            order_uuid = uuid.UUID(request.order_id)
        except ValueError as e:
            return catalog_service_pb2.ReleaseItemResponse(
                success=False,
                error_message=f"Invalid UUID format: {e}",
            )

        async with async_session_maker() as session:
            async with session.begin():
                query = select(Item).where(Item.id == item_uuid).with_for_update()
                result = await session.execute(query)
                item = result.scalar_one_or_none()

                if not item:
                    return catalog_service_pb2.ReleaseItemResponse(
                        success=False,
                        error_message=f"Item '{request.item_id}' not found",
                    )

                if item.status == ItemStatus.RESERVED:
                    if item.reserved_by_order_id == order_uuid:
                        item.status = ItemStatus.ACTIVE
                        item.reserved_by_order_id = None
                        item.reserved_until_timestamp = None
                        session.add(item)
                        logger.info(f"Item {item_uuid} released by order {order_uuid} back to ACTIVE.")
                    else:
                        return catalog_service_pb2.ReleaseItemResponse(
                            success=False,
                            error_message="Reservation held by a different order",
                        )

        return catalog_service_pb2.ReleaseItemResponse(success=True)

    async def MarkItemSold(
        self,
        request: catalog_service_pb2.MarkItemSoldRequest,
        context: grpc.aio.ServicerContext,
    ) -> catalog_service_pb2.ItemResponse:
        """Finalize order completion by marking the item SOLD."""
        try:
            item_uuid = uuid.UUID(request.item_id)
        except ValueError:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid item UUID")

        async with async_session_maker() as session:
            async with session.begin():
                query = select(Item).where(Item.id == item_uuid).with_for_update()
                result = await session.execute(query)
                item = result.scalar_one_or_none()

                if not item:
                    await context.abort(grpc.StatusCode.NOT_FOUND, "Item not found")

                item.status = ItemStatus.SOLD
                item.reserved_until_timestamp = None
                session.add(item)

        return item_to_proto(item)

    async def VisualSearch(
        self,
        request: catalog_service_pb2.VisualSearchRequest,
        context: grpc.aio.ServicerContext,
    ) -> catalog_service_pb2.VisualSearchResponse:
        """Execute pgvector similarity search over gRPC."""
        embedding = list(request.query_embedding)
        if len(embedding) != 512:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Embedding must be exactly 512 dimensions")

        limit = request.limit if request.limit > 0 else 10
        distance_col = Item.embedding.cosine_distance(embedding).label("distance")

        async with async_session_maker() as session:
            query = (
                select(Item, distance_col)
                .where(Item.status == ItemStatus.ACTIVE)
                .where(Item.embedding.isnot(None))
            )
            if request.category_filter:
                query = query.where(Item.category == request.category_filter)

            query = query.order_by(distance_col.asc()).limit(limit)
            result = await session.execute(query)
            rows = result.all()

            scored_items = []
            for item, dist in rows:
                sim = max(0.0, 1.0 - (float(dist) / 2.0))
                scored_items.append(
                    catalog_service_pb2.ScoredItem(
                        item=item_to_proto(item),
                        similarity_score=sim,
                    )
                )

        return catalog_service_pb2.VisualSearchResponse(items=scored_items)
