"""Main entrypoint for rewearit-ai-worker service."""
import asyncio
import signal
import sys
from typing import Any

import uvicorn

from app.core.config import settings
from app.core.logging import logger
from app.core.telemetry import init_tracer, instrument_app
from app.server import app as probe_app
from app.server import set_healthy, set_ready
from app.worker import AIAppraisalWorker


async def run_server() -> None:
    config = uvicorn.Config(
        probe_app,
        host="0.0.0.0",
        port=settings.HEALTH_PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    logger.info(f"Initializing {settings.SERVICE_NAME} (env={settings.ENVIRONMENT})...")

    # Initialize OpenTelemetry distributed tracing
    init_tracer(settings.SERVICE_NAME)
    instrument_app(probe_app)

    # Start health probe server in background
    probe_task = asyncio.create_task(run_server())

    worker = AIAppraisalWorker()
    stop_event = asyncio.Event()

    def _signal_handler(*_: Any) -> None:
        logger.info("Shutdown signal received. Initiating graceful shutdown...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        await worker.start()
        set_ready(True)
        set_healthy(True)
        logger.info(f"{settings.SERVICE_NAME} running. Health probes on :{settings.HEALTH_PORT}.")

        await stop_event.wait()
    except Exception as e:
        logger.critical(f"Fatal error in worker execution: {e}", exc_info=True)
        set_healthy(False)
    finally:
        set_ready(False)
        logger.info("Cleaning up worker resources...")
        await worker.stop()
        probe_task.cancel()
        try:
            await probe_task
        except asyncio.CancelledError:
            pass
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
