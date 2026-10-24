"""Unit tests for OpenTelemetry helper and Kafka header propagation."""
from fastapi import FastAPI
from opentelemetry import trace

from app.core.telemetry import (
    extract_kafka_context,
    init_tracer,
    inject_kafka_headers,
    instrument_app,
)


def test_init_tracer_returns_valid_tracer() -> None:
    tracer = init_tracer("test-ai-worker")
    assert tracer is not None
    assert isinstance(tracer, trace.Tracer)


def test_instrument_app_without_endpoint() -> None:
    app = FastAPI()
    instrument_app(app)


def test_kafka_header_injection_and_extraction() -> None:
    headers: list[tuple[str, bytes]] = [
        ("event_type", b"item.created"),
        ("correlation_id", b"123-abc"),
    ]
    tracer = init_tracer("test-ai-worker")
    with tracer.start_as_current_span("test-span"):
        injected = inject_kafka_headers(headers)
        assert len(injected) >= len(headers)
        extracted_ctx = extract_kafka_context(injected)
        assert extracted_ctx is not None
