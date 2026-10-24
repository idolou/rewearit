# ReWearIt Catalog Service (`rewearit-catalog-service`)

Core catalog, inventory management, and semantic visual search microservice for the **ReWearIt** platform.

## Features
- **REST API (Port 8001)**: Item creation, queries, category filtering, and visual embedding search.
- **gRPC API (Port 50051)**: High-speed inter-service inventory operations (`GetItem`, `ReserveItem`, `ReleaseItem`, `MarkItemSold`) with strict 1-of-1 concurrency locks.
- **PostgreSQL 16 + pgvector**: Native 512-dimensional vector similarity indexing (HNSW) for visual search.
- **Kafka Event Streaming**: Publishes `ItemCreatedEvent` (`item.created`) and consumes `AIAppraisalCompletedEvent` (`ai.appraisal_completed`).

## Quickstart
```bash
# Run with Docker
docker build -t rewearit-catalog-service:local .
docker run -p 8001:8001 -p 50051:50051 --env-file .env rewearit-catalog-service:local
```
