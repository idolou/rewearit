"""Async gRPC Server startup and lifecycle."""
import grpc

from app.core.config import settings
from app.core.logging import logger
from app.grpc.catalog_servicer import CatalogServicer
from app.grpc.schemas import catalog_service_pb2_grpc


class GrpcServer:
    def __init__(self) -> None:
        self.server: grpc.aio.Server | None = None

    async def start(self) -> None:
        """Start async gRPC server on configured host and port."""
        bind_address = f"{settings.GRPC_HOST}:{settings.GRPC_PORT}"
        logger.info(f"Starting gRPC server on {bind_address}...")
        self.server = grpc.aio.server()
        catalog_service_pb2_grpc.add_CatalogServiceServicer_to_server(
            CatalogServicer(),
            self.server,
        )
        self.server.add_insecure_port(bind_address)
        await self.server.start()
        logger.info(f"gRPC server successfully listening on {bind_address}.")

    async def stop(self) -> None:
        """Gracefully stop gRPC server."""
        if self.server:
            logger.info("Stopping gRPC server...")
            await self.server.stop(grace=5.0)
            self.server = None
            logger.info("gRPC server stopped.")


grpc_server = GrpcServer()
