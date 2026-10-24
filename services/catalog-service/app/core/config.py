"""Application configuration management using Pydantic Settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SERVICE_NAME: str = "rewearit-catalog-service"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # REST & gRPC Server bindings
    REST_HOST: str = "0.0.0.0"
    REST_PORT: int = 8001
    GRPC_HOST: str = "0.0.0.0"
    GRPC_PORT: int = 50051

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://catalog_user:catalog_password@localhost:5432/catalog_db"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Kafka Messaging
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_ITEM_EVENTS_TOPIC: str = "rewearit.items.events"
    KAFKA_AI_EVENTS_TOPIC: str = "rewearit.ai.events"
    KAFKA_ORDER_EVENTS_TOPIC: str = "rewearit.orders.events"
    CONSUMER_GROUP_CATALOG_SYNC: str = "cg-catalog-syncer"

    # S3 Object Storage (MinIO)
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_BUCKET_GARMENTS: str = "rewearit-garments"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadminpassword"

    # AI Worker Service
    AI_WORKER_URL: str = "http://localhost:8002"


settings = Settings()
