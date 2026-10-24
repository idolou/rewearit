"""OpenTelemetry distributed tracing initialization and Kafka context propagation."""
import os
from typing import Any

from fastapi import FastAPI
from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Tracer

from app.core.logging import logger

_tracer_initialized = False


def init_tracer(service_name: str) -> Tracer:
    """Initialize OpenTelemetry tracer provider with OTLP gRPC exporter if endpoint configured."""
    global _tracer_initialized

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint and not _tracer_initialized:
        logger.info(f"Initializing OpenTelemetry OTLP exporter to {otlp_endpoint} for {service_name}...")
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        insecure = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() in ("true", "1")
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=insecure)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer_initialized = True
        logger.info("OpenTelemetry tracer provider successfully registered.")

    return trace.get_tracer(service_name)


def instrument_app(app: FastAPI) -> None:
    """Instrument FastAPI application with OpenTelemetry middleware."""
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        try:
            FastAPIInstrumentor.instrument_app(app)
            logger.info("FastAPI OpenTelemetry instrumentation active.")
        except Exception as e:
            logger.warning(f"Could not instrument FastAPI with OpenTelemetry: {e}")


def inject_kafka_headers(headers: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    """Inject W3C traceparent context into Kafka message headers."""
    carrier: dict[str, str] = {}
    propagate.inject(carrier)

    new_headers = list(headers)
    for k, v in carrier.items():
        new_headers.append((k, v.encode("utf-8")))
    return new_headers


def extract_kafka_context(headers: list[tuple[str, bytes]]) -> Any:
    """Extract W3C trace context from Kafka message headers."""
    carrier: dict[str, str] = {}
    for k, v in headers:
        carrier[k] = v.decode("utf-8") if isinstance(v, bytes) else str(v)
    return propagate.extract(carrier)
