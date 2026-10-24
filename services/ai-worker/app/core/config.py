"""Configuration settings for rewearit-ai-worker."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    SERVICE_NAME: str = "rewearit-ai-worker"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    HEALTH_PORT: int = 8002

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_ITEMS_TOPIC: str = "rewearit.items.events"
    KAFKA_AI_EVENTS_TOPIC: str = "rewearit.ai.events"
    CONSUMER_GROUP_AI_WORKER: str = "cg-ai-worker"

    # Redis Caching
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = 86400 * 7  # 7 days

    # MinIO / S3 Storage
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_PUBLIC_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadminpassword"
    S3_BUCKET_GARMENTS: str = "rewearit-garments"

    # Model Pipelines
    VLM_PROVIDER: str = "heuristic"  # "heuristic", "gemini"
    GEMINI_API_KEY: str | None = None
    EMBEDDING_DIMENSION: int = 512


settings = Settings()
