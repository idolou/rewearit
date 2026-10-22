# `rewearit-catalog-service` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the production-grade `rewearit-catalog-service` microservice providing REST listing APIs, pgvector visual search, gRPC inventory management with 1-of-1 reservation locks, and Kafka event publishing/consumption.

**Architecture:** A standalone Python 3.12+ microservice adhering to `docs/agent-instructions/AGENTS.md`. Built on FastAPI (REST on port 8001), gRPC (asyncio servicer on port 50051), SQLModel/asyncpg over PostgreSQL 16 with `pgvector`, and `aiokafka` for Kafka event streaming.

**Tech Stack:** Python 3.12, FastAPI, SQLModel / SQLAlchemy, asyncpg, pgvector-python, grpcio / grpcio-tools, aiokafka, pydantic v2, pytest.

**Spec:** [docs/superpowers/specs/2026-10-17-rewearit-platform-design.md](file:///Users/idonewold/IDO/Projects/rewearit/docs/superpowers/specs/2026-10-17-rewearit-platform-design.md) & [docs/architecture/service-boundaries.md](file:///Users/idonewold/IDO/Projects/rewearit/docs/architecture/service-boundaries.md).

## Global Constraints

- **Python Floor:** Python 3.12+ with full type annotations.
- **Strict Domain Boundaries:** Never connect to `orders_db` or `pricing_db`.
- **Contracts:** Must use generated Protobuf schemas matching `docs/schemas/events.proto` and `docs/schemas/catalog_service.proto`.
- **Ports:** REST API on `8001`, gRPC on `50051`.
- **Idempotency & Concurrency:** Concurrency-safe item reservation locking ensuring 1-of-1 secondhand garment semantics.

## Review Focus

1. **pgvector index behavior:** Cosine distance `<->` operator queries against 512-dim vectors must execute properly without type mismatch.
2. **Double reservation race condition:** Two concurrent `ReserveItem` requests for the same available item must result in exactly one success and one failure.
3. **Draft / Analyzing status transition:** New items must enter `ANALYZING` and only become `ACTIVE` upon receiving `AIAppraisalCompletedEvent`.
4. **Protobuf serialization:** Kafka messages must serialize using the generated `EventHeader` envelope and protobuf payload.
5. **No hardcoded secrets:** Config must load from environment variables with sensible defaults for local development.

---

### Task 1: Scaffolding, Package Configuration & Dockerfile

**Files:**
- Create: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/pyproject.toml`
- Create: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/Dockerfile`
- Create: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/README.md`
- Create: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/app/core/config.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/app/core/logging.py`
- Test: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/tests/unit/test_config.py`

- [ ] Create directory structure adhering to Section 3 of `AGENTS.md`.
- [ ] Define `pyproject.toml` with dependencies: `fastapi`, `uvicorn`, `sqlmodel`, `asyncpg`, `pgvector`, `aiokafka`, `grpcio`, `pydantic-settings`, `pytest`, `pytest-asyncio`, `httpx`.
- [ ] Implement `Settings` using Pydantic Settings loading `DATABASE_URL`, `KAFKA_BOOTSTRAP_SERVERS`, `GRPC_PORT`, `REST_PORT`, `S3_BUCKET`.
- [ ] Write unit tests for configuration loading and defaults.
- [ ] Commit: `feat(catalog): scaffold service, configuration, and dependencies`.

---

### Task 2: Domain Entities & Database Layer (pgvector)

**Files:**
- Create: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/app/models/item.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/app/core/database.py`
- Test: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/tests/unit/test_models.py`
- Test: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/tests/integration/test_db_pgvector.py`

- [ ] Define `ConditionGrade` and `ItemStatus` enums aligning with Protobuf.
- [ ] Define `Item` SQLModel with UUID primary key, seller info, category, brand, size, condition, price fields (`currency`, `units`, `nanos`), `image_urls` (JSON), and `embedding` (Vector(512)).
- [ ] Configure async SQLAlchemy engine and session dependency for `postgresql+asyncpg://catalog_user:catalog_password@localhost:5432/catalog_db`.
- [ ] Write unit test verifying entity serialization and status validation.
- [ ] Write integration test verifying connection to local `catalog_db` and HNSW/cosine distance vector query execution.
- [ ] Commit: `feat(catalog): implement SQLModel domain entities and pgvector database layer`.

---

### Task 3: Kafka Event Producers & Consumers

**Files:**
- Create: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/app/events/producer.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/app/events/consumer.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/app/events/schemas.py`
- Test: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/tests/unit/test_events.py`

- [ ] Implement `KafkaEventProducer` with `publish_item_created(item: Item)` producing to `rewearit.items.events` with `ItemCreatedEvent` payload.
- [ ] Implement `KafkaEventConsumer` handling `rewearit.ai.events` (`AIAppraisalCompletedEvent`) to update item attributes, embedding, and activate status.
- [ ] Handle `rewearit.orders.events` (`OrderCompletedEvent` -> mark SOLD, `OrderCancelledEvent` -> release reservation).
- [ ] Write tests verifying serialization/deserialization into Protobuf envelopes.
- [ ] Commit: `feat(catalog): implement Kafka event producer and consumer with protobuf contracts`.

---

### Task 4: REST API (FastAPI)

**Files:**
- Create: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/app/api/v1/items.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/app/services/catalog_service.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/app/main.py`
- Test: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/tests/unit/test_items_api.py`

- [ ] Implement `POST /api/v1/items`: Creates listing in `ANALYZING` status and dispatches `ItemCreatedEvent` to Kafka.
- [ ] Implement `GET /api/v1/items/{item_id}`: Retrieves single item by ID.
- [ ] Implement `GET /api/v1/items`: Filtered search by category, brand, condition, and status.
- [ ] Implement `POST /api/v1/items/search/visual`: Accepts 512-dim embedding and returns top-K nearest active items using cosine distance `<->`.
- [ ] Implement health check `/healthz` and `/ready`.
- [ ] Write API unit tests with mock database/Kafka verifying request validation and responses.
- [ ] Commit: `feat(catalog): implement FastAPI REST endpoints for listings and visual search`.

---

### Task 5: gRPC Service Implementation (Atomic 1-of-1 Reservation)

**Files:**
- Create: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/app/grpc/server.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/app/grpc/catalog_servicer.py`
- Test: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/tests/unit/test_grpc_servicer.py`

- [ ] Implement `CatalogServiceServicer` adhering to `catalog_service_pb2_grpc.CatalogServiceServicer`.
- [ ] Implement `GetItem(GetItemRequest)` returning `ItemResponse`.
- [ ] Implement `ReserveItem(ReserveItemRequest)`: Uses SQL transaction with `SELECT ... FOR UPDATE` ensuring atomic reservation lock. Fails if item is already reserved or sold.
- [ ] Implement `ReleaseItem(ReleaseItemRequest)`: Releases reservation if expired or cancelled.
- [ ] Implement `MarkItemSold(MarkItemSoldRequest)`: Transitions item from `RESERVED` to `SOLD`.
- [ ] Implement `VisualSearch(VisualSearchRequest)`.
- [ ] Write unit tests for gRPC methods verifying concurrency safety and error codes.
- [ ] Commit: `feat(catalog): implement async gRPC servicer with atomic reservation locking`.

---

### Task 6: Integration Testing & Verification

**Files:**
- Create: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/tests/integration/test_catalog_e2e.py`
- Modify: `/Users/idonewold/IDO/Projects/rewearit/README.md`
- Modify: `/Users/idonewold/IDO/Projects/rewearit-catalog-service/Dockerfile`

- [ ] Run full test suite (`pytest`) verifying all unit and integration tests pass.
- [ ] Build Docker image `rewearit-catalog-service:local` verifying multi-stage build succeeds.
- [ ] Verify live end-to-end flow: Create item via REST -> verify row in PostgreSQL `catalog_db` -> verify vector search -> test gRPC `ReserveItem`.
- [ ] Commit: `test(catalog): add end-to-end verification and production Dockerfile`.
