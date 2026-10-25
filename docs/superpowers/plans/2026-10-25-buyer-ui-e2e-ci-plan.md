# Buyer Catalog UI, E2E Smoke Suite, and GitHub Actions CI/CD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
Build the full buyer marketplace journey with pgvector visual search, an end-to-end automated smoke & trace verification suite, and a production-grade GitHub Actions CI/CD pipeline.

**Architecture:**
1. **Buyer Catalog & Visual Search UI:** Serves `/` and `/explore` from `catalog-service`, integrating visual image-to-embedding search via `ai-worker:8002/api/v1/embeddings` and pgvector cosine distance, with modal checkout invoking `order-service:8003` escrow locking.
2. **End-to-End Smoke & Trace Verification:** `scripts/verify_e2e.py` and integration tests validating the full multi-service transaction cycle (Studio intake -> Visual search -> gRPC 1-of-1 lock -> Escrow completion -> Jaeger trace assertion).
3. **CI/CD Automation:** GitHub Actions workflow executing linting (`ruff`), type-checking (`mypy`), unit/integration testing, and Docker builds across the monorepo.

**Tech Stack:** Python 3.12, FastAPI, Vanilla Modern CSS/JS, OpenTelemetry/Jaeger, Redpanda, Redis, PostgreSQL/pgvector, GitHub Actions.

---

## Tasks

### Task 1: AI Worker Image Embedding Endpoint & Catalog Visual Image Search Proxy
**Files:**
- Modify: `services/ai-worker/app/server.py` (add `POST /api/v1/embeddings`)
- Modify: `services/catalog-service/app/api/v1/items.py` (add `POST /api/v1/items/search/visual-image`)
- Test: `services/ai-worker/tests/integration/test_embeddings_api.py`
- Test: `services/catalog-service/tests/unit/test_visual_image_search.py`

- [x] Write failing test for `POST /api/v1/embeddings` in `ai-worker`.
- [x] Implement `POST /api/v1/embeddings` in `ai-worker/app/server.py` returning `{"embedding": list[float], "dimension": 512}`.
- [x] Write failing test for `POST /api/v1/items/search/visual-image` in `catalog-service`.
- [x] Implement `POST /api/v1/items/search/visual-image` in `catalog-service/app/api/v1/items.py` accepting multipart image or image URL, retrieving embedding from `ai-worker`, and querying pgvector cosine similarity.
- [x] Run pytest on both services and verify all pass.
- [x] Commit: `feat(api): expose visual embedding and photo-search endpoints`.

---

### Task 2: Buyer Catalog & Visual Search Web UI (`/` and `/explore`)
**Files:**
- Create: `services/catalog-service/app/static/buyer_catalog.html`
- Modify: `services/catalog-service/app/main.py` (serve buyer UI at `/` and `/explore`)
- Test: `services/catalog-service/tests/unit/test_buyer_ui.py`

- [x] Write failing test verifying `GET /` and `GET /explore` return `text/html` with buyer catalog page.
- [x] Build `services/catalog-service/app/static/buyer_catalog.html`:
  - Marketplace header with ReWearIt branding and navigation links (`Explore`, `Sell an Item / Studio`).
  - Search & Filter bar: Category pills (`All`, `Tops`, `Bottoms`, `Outerwear`, `Footwear`, `Accessories`, `Dresses`), Brand input, Condition filter, Price range filter.
  - "Search by Photo" drag-and-drop drawer: Upload photo -> calls `POST /api/v1/items/search/visual-image` -> updates item grid with similarity badges (`98% Match`).
  - Responsive Garment Grid: Clean card tiles with studio-framed catalog images, title, brand, size, condition, and price in USD.
  - Checkout Modal: "Buy & Lock Escrow" button calling `order-service:8003/api/v1/orders`, with idempotency key generation and escrow explanation.
- [x] Register routes in `services/catalog-service/app/main.py`.
- [x] Run pytest to verify all tests pass.
- [x] Commit: `feat(catalog): implement buyer catalog and visual search web interface`.

---

### Task 3: Automated End-to-End Smoke & Tracing Verification Suite
**Files:**
- Create: `scripts/verify_e2e.py`
- Create: `tests/e2e/test_platform_lifecycle.py`
- Modify: `pyproject.toml` (root monorepo or runner config)
- Test: `pytest tests/e2e/test_platform_lifecycle.py`

- [x] Write `scripts/verify_e2e.py`:
  1. Uploads synthetic sample garment to `catalog-service:8001/api/v1/items/classify`.
  2. Publishes item to `POST /api/v1/items`.
  3. Executes `POST /api/v1/items/search/visual-image` and verifies similarity.
  4. Places order with idempotency key via `POST http://localhost:8003/api/v1/orders` (asserts status `ESCROW_HELD`).
  5. Attempts concurrent duplicate order (asserts `409 Conflict` "Item is currently reserved").
  6. Completes order via `POST http://localhost:8003/api/v1/orders/{id}/complete` (asserts `COMPLETED` and item status `SOLD`).
  7. Queries Jaeger trace API (`http://localhost:16686/api/traces`) to verify end-to-end trace propagation.
- [x] Write unit/mock-based e2e test in `tests/e2e/test_platform_lifecycle.py` so the test passes cleanly in CI without live Docker daemon while `verify_e2e.py` works against the live mesh.
- [x] Run pytest and verify all pass.
- [x] Commit: `feat(e2e): add automated multi-service smoke and trace verification suite`.

---

### Task 4: GitHub Actions CI/CD Pipeline
**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md` (add CI badge and instructions)

- [x] Create `.github/workflows/ci.yml`:
  - `lint`: runs `ruff check` on all 3 services.
  - `typecheck`: runs `mypy` on all 3 services.
  - `test`: matrix job running `pytest` with `uv` on Python 3.12 across `catalog-service`, `ai-worker`, and `order-service`.
  - `docker-build`: verifies Dockerfiles build successfully for all services.
- [x] Validate workflow syntax and test locally with `ruff` and `pytest`.
- [x] Update `README.md` with CI badge and quick links.
- [ ] Commit & push to GitHub `idolou/rewearit`.
