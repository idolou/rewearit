# `rewearit-ai-worker` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the asynchronous intelligence processor `rewearit-ai-worker` that consumes `item.created` Kafka events, extracts garment attributes, determines condition grades, computes 512-dimensional multimodal visual embeddings, and publishes `AIAppraisalCompletedEvent` on `rewearit.ai.events`.

**Architecture:** A standalone Python 3.12+ microservice worker adhering to `docs/agent-instructions/AGENTS.md`. Built on `asyncio`, `aiokafka`, `redis-py` (async), `pillow`, pluggable VLM & Embedding pipelines, and a lightweight FastAPI HTTP status server (for `/healthz` and `/ready` probes on port `8002`). Dependency management and multi-stage containerization with `uv`.

**Tech Stack:** Python 3.12+, uv, aiokafka, redis, pillow, pydantic v2, pydantic-settings, protobuf, httpx, pytest, pytest-asyncio, ruff, mypy.

**Spec:** [docs/architecture/ai-multimodal-pipeline.md](file:///Users/idonewold/IDO/Projects/rewearit/docs/architecture/ai-multimodal-pipeline.md) & [docs/schemas/events.proto](file:///Users/idonewold/IDO/Projects/rewearit/docs/schemas/events.proto).

---

## Global Constraints

- **Python Floor:** Python 3.12+ with full type annotations.
- **Strict Domain Boundaries:** Never connect to `catalog_db`, `orders_db`, or `pricing_db`. Microservice communicates purely through Kafka events and Redis.
- **Contract-First:** Must use generated Protobuf schemas matching `rewearit/docs/schemas/events.proto`.
- **Package Management:** Fast, deterministic dependency management using `uv` (`pyproject.toml`, `uv.lock`, multi-stage `Dockerfile`).
- **Resilience & Fallback:** Circuit breaker pattern for external VLM calls, SHA-256 caching in Redis to prevent duplicate compute, graceful fallback to local heuristic appraisal if external APIs fail or are offline.
- **Observability:** Health probe server on port `8002` (`/healthz`, `/ready`), structured JSON logging.

---

## Task Decomposition

### Task 1: Scaffolding, Package Configuration (`uv`) & Health Probes

**Files:**
- Create: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/pyproject.toml`
- Create: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/Dockerfile`
- Create: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/README.md`
- Create: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/app/core/config.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/app/core/logging.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/app/server.py`
- Test: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/tests/unit/test_config.py`
- Test: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/tests/unit/test_health.py`

- [x] Initialize git repo at `/Users/idonewold/IDO/Projects/rewearit-ai-worker`.
- [x] Define `pyproject.toml` with `uv` dependencies: `aiokafka`, `redis`, `pillow`, `pydantic-settings`, `httpx`, `fastapi`, `uvicorn`, `protobuf`, `pytest`, `pytest-asyncio`, `ruff`, `mypy`.
- [x] Implement `Settings` loading `KAFKA_BOOTSTRAP_SERVERS`, `REDIS_URL`, `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `VLM_PROVIDER`, `HEALTH_PORT=8002`.
- [x] Implement lightweight FastAPI probe server on `HEALTH_PORT` providing `/healthz` and `/ready`.
- [x] Build multi-stage `Dockerfile` with `ghcr.io/astral-sh/uv:latest` and non-root `appuser`.
- [x] Write unit tests verifying config defaults and health endpoints.
- [x] Run `ruff check`, `mypy`, and `pytest`.
- [x] Commit: `feat(worker): scaffold rewearit-ai-worker with uv and health server`.

---

### Task 2: Protobuf Event Schemas & Kafka Consumer/Producer Envelope

**Files:**
- Create: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/app/events/schemas.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/app/events/producer.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/app/events/consumer.py`
- Copy/Compile: Protobuf stubs `events_pb2.py` from central schema.
- Test: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/tests/unit/test_events_serialization.py`

- [x] Compile or bundle `events_pb2.py` matching `rewearit/docs/schemas/events.proto`.
- [x] Implement `AIEventProducer` publishing `AIAppraisalCompletedEvent` to `rewearit.ai.events` with standard `EventHeader`.
- [x] Implement `ItemEventConsumer` subscribing to `rewearit.items.events` (group `cg-ai-worker`).
- [x] Write unit test verifying serialization/deserialization of `ItemCreatedEvent` and `AIAppraisalCompletedEvent`.
- [x] Commit: `feat(worker): implement protobuf event envelope and kafka producer/consumer`.

---

### Task 3: Image Preprocessing & Caching Layer

**Files:**
- Create: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/app/pipeline/preprocessor.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/app/pipeline/cache.py`
- Test: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/tests/unit/test_preprocessor.py`
- Test: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/tests/unit/test_cache.py`

- [x] Implement `ImagePreprocessor`: fetches image bytes from S3/MinIO or HTTP URL, strips EXIF metadata, resizes to standard 1024x1024 or converts to WebP, and calculates SHA-256 hash.
- [x] Implement `AppraisalCache`: Redis-backed caching keyed by `ai:appraisal:<sha256>` with TTL to prevent redundant VLM and embedding calls.
- [x] Write unit tests verifying EXIF stripping, hashing, and cache hits/misses with mock Redis.
- [x] Commit: `feat(worker): implement image preprocessor and sha-256 redis caching`.

---

### Task 4: VLM Attribute Extraction & Visual Embedding Generation

**Files:**
- Create: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/app/pipeline/vlm/base.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/app/pipeline/vlm/heuristic.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/app/pipeline/vlm/gemini.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/app/pipeline/embeddings/base.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/app/pipeline/embeddings/encoder.py`
- Test: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/tests/unit/test_vlm.py`
- Test: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/tests/unit/test_embeddings.py`

- [x] Define `VLMClient` protocol returning `VLMAppraisalResult` (brand, category, condition grade, confidence, tags, suggested min/max price).
- [x] Implement `HeuristicVLMClient` resilient fallback parser (uses title, description, and image heuristic features for deterministic offline execution).
- [x] Implement `GeminiVLMClient` for Google Gemini vision API with structured output schema.
- [x] Implement `EmbeddingEncoder`: produces 512-dimensional L2-normalized float vectors (norm == 1.0) suitable for cosine distance in `pgvector`.
- [x] Write unit tests verifying 512-dim length, L2-norm == 1.000, and condition grading mapping.
- [x] Commit: `feat(worker): implement vlm attribute extraction and 512-dim embedding encoder`.

---

### Task 5: End-to-End Worker Orchestration & Lifecycle

**Files:**
- Create: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/app/main.py`
- Create: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/app/worker.py`
- Test: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/tests/unit/test_worker.py`
- Test: `/Users/idonewold/IDO/Projects/rewearit-ai-worker/tests/integration/test_worker_pipeline.py`

- [x] Implement `AIAppraisalWorker`: orchestrates receiving `ItemCreatedEvent`, checking cache, invoking preprocessor, VLM, and embedding encoder, caching result, and emitting `AIAppraisalCompletedEvent`.
- [x] Implement graceful startup and shutdown hooks handling SIGTERM/SIGINT.
- [x] Write unit and integration tests simulating an incoming `ItemCreatedEvent` and asserting an `AIAppraisalCompletedEvent` is emitted.
- [x] Commit: `feat(worker): implement full worker lifecycle and pipeline orchestration`.

---

### Task 6: Full Integration & Container Smoke Test with Catalog Service

**Files:**
- Modify: `rewearit/deploy/docker-compose/docker-compose.yml` (add `catalog-service` and `ai-worker` services)
- Test: Live end-to-end event loop: Item Created -> AI Appraisal Emitted -> Catalog Item Updated to ACTIVE with embedding.

- [x] Lock dependencies with `uv lock` in `rewearit-ai-worker`.
- [x] Build Docker image `rewearit-ai-worker:local`.
- [x] Test the live pipeline: Create item via Catalog Service -> AI Worker picks it up -> AI Worker generates 512-dim vector & condition -> Catalog Service consumes appraisal and activates item in `catalog_db` with pgvector embedding.
- [x] Commit: `test(worker): verify end-to-end multimodal pipeline with catalog service`.
