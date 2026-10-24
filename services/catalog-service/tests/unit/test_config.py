"""Unit tests for configuration loading."""
from app.core.config import Settings


def test_default_settings() -> None:
    config = Settings()
    assert config.SERVICE_NAME == "rewearit-catalog-service"
    assert config.REST_PORT == 8001
    assert config.GRPC_PORT == 50051
    assert "catalog_db" in config.DATABASE_URL
    assert config.KAFKA_BOOTSTRAP_SERVERS == "localhost:9092"
    assert config.KAFKA_ITEM_EVENTS_TOPIC == "rewearit.items.events"


def test_custom_settings_override() -> None:
    config = Settings(REST_PORT=9005, LOG_LEVEL="DEBUG")
    assert config.REST_PORT == 9005
    assert config.LOG_LEVEL == "DEBUG"
