"""Async gRPC client for communicating with rewearit-catalog-service."""
import uuid
from dataclasses import dataclass

import grpc
from opentelemetry import trace

from app.core.config import settings
from app.core.logging import logger
from app.grpc.schemas import catalog_service_pb2, catalog_service_pb2_grpc

tracer = trace.get_tracer("rewearit-order-service")


@dataclass
class CatalogItemSnapshot:
    item_id: uuid.UUID
    seller_id: uuid.UUID
    price_units: int
    price_nanos: int
    currency: str


class ReservationResult:
    def __init__(self, success: bool, error_message: str = "", expires_at_timestamp: int = 0) -> None:
        self.success = success
        self.error_message = error_message
        self.expires_at_timestamp = expires_at_timestamp


class CatalogGrpcClient:
    def __init__(self, target: str | None = None) -> None:
        self.target = target or settings.CATALOG_GRPC_TARGET
        self._channel: grpc.aio.Channel | None = None
        self._stub: catalog_service_pb2_grpc.CatalogServiceStub | None = None

    def _get_stub(self) -> catalog_service_pb2_grpc.CatalogServiceStub:
        if self._channel is None or self._stub is None:
            self._channel = grpc.aio.insecure_channel(self.target)
            self._stub = catalog_service_pb2_grpc.CatalogServiceStub(self._channel)
        return self._stub

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._stub = None

    async def get_item(self, item_id: uuid.UUID) -> CatalogItemSnapshot | None:
        """Fetch authoritative price and seller for an item via CatalogService.GetItem."""
        with tracer.start_as_current_span("grpc.catalog.GetItem") as span:
            span.set_attribute("item.id", str(item_id))
            try:
                stub = self._get_stub()
                req = catalog_service_pb2.GetItemRequest(item_id=str(item_id))
                resp = await stub.GetItem(req, timeout=5.0)
                return CatalogItemSnapshot(
                    item_id=uuid.UUID(resp.item_id),
                    seller_id=uuid.UUID(resp.seller_id),
                    price_units=int(resp.price.units),
                    price_nanos=int(resp.price.nanos),
                    currency=resp.price.currency or "USD",
                )
            except Exception as e:
                logger.error(f"Failed to fetch item {item_id} via gRPC GetItem: {e}")
                span.record_exception(e)
                return None

    async def reserve_item(
        self,
        item_id: uuid.UUID,
        order_id: uuid.UUID,
        buyer_id: uuid.UUID,
        ttl_seconds: int | None = None,
    ) -> ReservationResult:
        """Call CatalogService.ReserveItem to atomically reserve a 1-of-1 garment."""
        ttl = ttl_seconds or settings.RESERVATION_TTL_SECONDS
        with tracer.start_as_current_span("grpc.catalog.ReserveItem") as span:
            span.set_attribute("item.id", str(item_id))
            span.set_attribute("order.id", str(order_id))
            span.set_attribute("buyer.id", str(buyer_id))

            try:
                stub = self._get_stub()
                req = catalog_service_pb2.ReserveItemRequest(
                    item_id=str(item_id),
                    order_id=str(order_id),
                    buyer_id=str(buyer_id),
                    ttl_seconds=ttl,
                )
                logger.info(f"Invoking gRPC ReserveItem on {self.target} for item_id={item_id}")
                response = await stub.ReserveItem(req, timeout=5.0)

                span.set_attribute("reservation.success", response.success)
                if not response.success:
                    span.set_attribute("reservation.error", response.error_message)

                return ReservationResult(
                    success=response.success,
                    error_message=response.error_message,
                    expires_at_timestamp=response.expires_at_timestamp,
                )
            except grpc.RpcError as e:
                logger.error(f"gRPC ReserveItem RPC error on {self.target}: {e.code()} - {e.details()}")
                span.record_exception(e)
                return ReservationResult(success=False, error_message=f"RPC error: {e.details() or e.code()}")
            except Exception as e:
                logger.error(f"Unexpected error calling Catalog gRPC: {e}", exc_info=True)
                span.record_exception(e)
                return ReservationResult(success=False, error_message=str(e))

    async def release_item(
        self,
        item_id: uuid.UUID,
        order_id: uuid.UUID,
        reason: str = "order_cancelled",
    ) -> bool:
        """Call CatalogService.ReleaseItem to release reserved garment back to ACTIVE."""
        with tracer.start_as_current_span("grpc.catalog.ReleaseItem") as span:
            span.set_attribute("item.id", str(item_id))
            span.set_attribute("order.id", str(order_id))
            try:
                stub = self._get_stub()
                req = catalog_service_pb2.ReleaseItemRequest(
                    item_id=str(item_id),
                    order_id=str(order_id),
                    reason=reason,
                )
                response = await stub.ReleaseItem(req, timeout=5.0)
                return bool(response.success)
            except Exception as e:
                logger.error(f"Failed to release item {item_id} via gRPC: {e}")
                span.record_exception(e)
                return False

    async def mark_item_sold(
        self,
        item_id: uuid.UUID,
        order_id: uuid.UUID,
        buyer_id: uuid.UUID,
    ) -> bool:
        """Call CatalogService.MarkItemSold synchronously so Kafka hiccups cannot allow re-selling."""
        with tracer.start_as_current_span("grpc.catalog.MarkItemSold") as span:
            span.set_attribute("item.id", str(item_id))
            span.set_attribute("order.id", str(order_id))
            try:
                stub = self._get_stub()
                req = catalog_service_pb2.MarkItemSoldRequest(
                    item_id=str(item_id),
                    order_id=str(order_id),
                    buyer_id=str(buyer_id),
                )
                await stub.MarkItemSold(req, timeout=5.0)
                return True
            except Exception as e:
                logger.error(f"Failed to mark item {item_id} SOLD via gRPC: {e}")
                span.record_exception(e)
                return False
