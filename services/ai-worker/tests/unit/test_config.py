"""Unit tests for configuration loading."""
from app.core.config import Settings


def test_settings_defaults() -> None:
    settings = Settings()
    assert settings.SERVICE_NAME == "rewearit-ai-worker"
    assert settings.HEALTH_PORT == 8002
    assert settings.KAFKA_BOOTSTRAP_SERVERS == "localhost:9092"
    assert settings.CONSUMER_GROUP_AI_WORKER == "cg-ai-worker"
    assert settings.EMBEDDING_DIMENSION == 512
