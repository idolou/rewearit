"""Application configuration management for rewearit-order-service."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SERVICE_NAME: str = "rewearit-order-service"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # REST Server bindings
    REST_HOST: str = "0.0.0.0"
    REST_PORT: int = 8003

    # Database (PostgreSQL 16 orders_db)
    DATABASE_URL: str = "postgresql+asyncpg://orders_user:orders_password@localhost:5433/orders_db"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Redis (Idempotency and Locks)
    REDIS_URL: str = "redis://localhost:6379/0"
    IDEMPOTENCY_TTL_SECONDS: int = 86400

    # Catalog Service gRPC
    CATALOG_GRPC_TARGET: str = "localhost:50051"
    RESERVATION_TTL_SECONDS: int = 900  # 15 minutes default

    # Kafka Messaging
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_ORDERS_TOPIC: str = "rewearit.orders.events"

    # OpenTelemetry Tracing
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    OTEL_EXPORTER_OTLP_INSECURE: bool = True


settings = Settings()
