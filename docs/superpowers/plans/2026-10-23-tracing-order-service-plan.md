# Implementation Plan: Architecture Diagram, Distributed Tracing (Jaeger/OTel) & `rewearit-order-service`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
1. Upgrade `README.md` with rich Mermaid architecture diagrams (system topology, data flow, observability).
2. Establish end-to-end distributed tracing across the platform using Jaeger (`jaegertracing/all-in-one`) and OpenTelemetry (FastAPI, gRPC, Kafka header trace propagation).
3. Implement `rewearit-order-service` with atomic 1-of-1 garment reservation via gRPC to `catalog-service`, Redis idempotency, escrow state machine, and Kafka event publishing.

**Tech Stack:** Python 3.12+, uv, FastAPI, SQLModel/asyncpg over PostgreSQL 16 (`orders_db`), Redis (idempotency), OpenTelemetry SDK / Jaeger exporter (`4317/4318/16686`), grpcio, aiokafka, pytest.

---

## Tasks

### Task 1: Rich Mermaid Architecture Diagrams in README.md
**Files:**
- Modify: `rewearit/README.md`

- [x] Add a comprehensive Mermaid `graph TD` system architecture diagram displaying:
  - External clients / Gateway (FastAPI)
  - Core Services: `rewearit-catalog-service` (:8001 / :50051), `rewearit-order-service` (:8003 / :50052), `rewearit-ai-worker` (:8002)
  - Databases: `catalog_db` (pgvector 5432), `orders_db` (5433), `pricing_db` (5434), Redis (6379), MinIO (9000)
  - Messaging Mesh: Redpanda Kafka topics (`rewearit.items.events`, `rewearit.ai.events`, `rewearit.orders.events`)
  - Observability Mesh: Jaeger UI (:16686), OTLP Collector (:4317/:4318), Redpanda Console (:8080)
- [x] Add a Mermaid `sequenceDiagram` showing the end-to-end checkout & reservation flow:
  `Buyer -> Gateway -> Order Service -> [gRPC ReserveItem] -> Catalog Service (pgvector lock) -> Escrow Held -> Kafka Event`
- [x] Commit: `docs(readme): add rich mermaid architecture and order flow diagrams`.

---

### Task 2: Jaeger & OpenTelemetry Infrastructure in Docker Compose
**Files:**
- Modify: `rewearit/deploy/docker-compose/docker-compose.yml`

- [x] Add `jaeger` service (`jaegertracing/all-in-one:1.57`) to `docker-compose.yml`:
  - Ports: `16686:16686` (Web UI), `4317:4317` (OTLP gRPC), `4318:4318` (OTLP HTTP).
  - Connected to `rewearit-mesh`.
- [x] Add OpenTelemetry environment variables to existing services in `docker-compose.yml`:
  - `OTEL_EXPORTER_OTLP_ENDPOINT: http://jaeger:4317`
  - `OTEL_SERVICE_NAME`
- [x] Launch Jaeger and verify UI is responsive at `http://localhost:16686`.
- [x] Commit: `feat(infra): add jaeger and otlp tracing infrastructure to compose`.

---

### Task 3: Distributed Tracing Module for Services
**Files:**
- Create: `rewearit/docs/schemas/tracing.py` (reference helper for OTel setup & Kafka header propagation)
- Modify: `rewearit-catalog-service` to include `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-exporter-otlp`
- Modify: `rewearit-ai-worker` to include OTel trace instrumentation on Kafka message processing

- [x] Implement standardized OTel tracer configuration helper with automatic span creation.
- [x] Implement Kafka trace context carrier injector/extractor for distributed trace propagation across asynchronous event queues.
- [x] Verify spans appear in Jaeger for `catalog-service` and `ai-worker`.
- [x] Commit: `feat(tracing): implement distributed otel tracing across catalog and ai-worker`.

---

### Task 4: Scaffold `rewearit-order-service` with `uv` & Database Schema
**Files:**
- Create: `/Users/idonewold/IDO/Projects/rewearit-order-service/pyproject.toml`
- Create: `/Users/idonewold/IDO/Projects/rewearit-order-service/Dockerfile`
- Create: `/Users/idonewold/IDO/Projects/rewearit-order-service/README.md`
- Create: `/Users/idonewold/IDO/Projects/rewearit-order-service/app/core/config.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-order-service/app/core/database.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-order-service/app/models/order.py`
- Test: `/Users/idonewold/IDO/Projects/rewearit-order-service/tests/unit/test_order_models.py`

- [x] Initialize git repo at `/Users/idonewold/IDO/Projects/rewearit-order-service`.
- [x] Configure `pyproject.toml` with `uv`: `fastapi`, `uvicorn`, `sqlmodel`, `asyncpg`, `aiokafka`, `redis`, `grpcio`, `opentelemetry-sdk`, `pydantic-settings`, `pytest`.
- [x] Define `Order` SQLModel with `OrderStatus` enum (`CREATED`, `ESCROW_HELD`, `SHIPPED`, `DELIVERED`, `COMPLETED`, `CANCELLED`, `REFUNDED`), `total_amount_units`, `currency`, `idempotency_key`.
- [x] Write unit tests verifying model validation, state transitions, and database table creation.
- [x] Commit: `feat(orders): scaffold rewearit-order-service and domain models with uv`.

---

### Task 5: gRPC Catalog Client, Redis Idempotency & Order State Machine
**Files:**
- Create: `/Users/idonewold/IDO/Projects/rewearit-order-service/app/clients/catalog_client.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-order-service/app/services/idempotency.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-order-service/app/services/order_service.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-order-service/app/events/producer.py`
- Test: `/Users/idonewold/IDO/Projects/rewearit-order-service/tests/unit/test_order_service.py`

- [x] Implement `CatalogGrpcClient`: invokes `ReserveItem(item_id, order_id, reservation_timeout_seconds=900)` on `rewearit-catalog-service:50051`.
- [x] Implement `IdempotencyManager` using Redis with atomic `SET NX EX`.
- [x] Implement `OrderService.create_order`:
  - Validates `Idempotency-Key`.
  - Invokes `CatalogGrpcClient.reserve_item(item_id, order_id)`.
  - If reservation succeeds: creates order in `ESCROW_HELD`, commits to `orders_db`, and publishes `order.placed` & `order.escrow_locked` to `rewearit.orders.events`.
  - If reservation fails (item already reserved/sold): raises 409 Conflict.
- [x] Implement state transition endpoints (`ship_order`, `complete_order`, `cancel_order`).
- [x] Write unit tests with mocked gRPC client and Redis.
- [x] Commit: `feat(orders): implement gRPC catalog reservation, redis idempotency, and state machine`.

---

### Task 6: REST Endpoints, Docker Container Build & Live Integration
**Files:**
- Create: `/Users/idonewold/IDO/Projects/rewearit-order-service/app/api/v1/orders.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-order-service/app/main.py`
- Modify: `rewearit/deploy/docker-compose/docker-compose.yml` (add `order-service` on port 8003)
- Test: End-to-end checkout flow & distributed trace verification in Jaeger

- [x] Build Docker image `rewearit-order-service:local` with `uv`.
- [x] Launch `order-service` in `docker-compose`.
- [x] Execute live end-to-end test:
  1. Create garment in `catalog-service` -> `ai-worker` appraises and activates it.
  2. Create order in `order-service` with `Idempotency-Key` -> `order-service` calls `catalog-service` via gRPC to reserve item -> item becomes `RESERVED` in catalog.
  3. Attempt duplicate order for same item -> 409 Conflict (item already reserved).
  4. Complete order in `order-service` -> `order.completed` published -> `catalog-service` consumes event and marks item as `SOLD`!
  5. Inspect distributed trace in Jaeger UI (`http://localhost:16686`) covering HTTP -> gRPC -> Kafka -> Database!
- [x] Commit: `test(orders): verify live checkout, atomic gRPC reservation, and distributed tracing`.
