# ADR 0006: Monorepo Consolidation for Microservices & Contracts

- **Status**: Accepted
- **Date**: 2026-10-24
- **Deciders**: Ido Lourie
- **Supersedes**: ADR 0001 (Polyrepo Strategy)

## Context
Initial platform design explored a polyrepo layout with independent repositories per microservice (`catalog-service`, `ai-worker`, `order-service`) and a coordinating architecture repository.

In practice, managing multiple separate repositories introduced friction:
1. Coordinated pull requests across 4 separate repositories whenever shared Protobuf contracts were updated.
2. Complicated local developer onboarding and CI orchestration.
3. Fragmented git histories for platform-wide features.

## Decision
Consolidate all microservices and shared contracts into a **modular monorepo** under `rewearit`:
- `contracts/`: Canonical Protobuf schemas (`events.proto`, `catalog_service.proto`).
- `services/catalog-service/`: Catalog API and pgvector vector search.
- `services/ai-worker/`: Asynchronous multimodal VLM intelligence worker.
- `services/order-service/`: Order transactions, Redis idempotency, and escrow state machine.
- `deploy/docker-compose/`: Unified local development cluster.

## Consequences
### Positive
- **Single Source of Truth:** One repository to clone, branch, PR, and review.
- **Atomic Commits:** Protobuf contract changes and service implementations are updated in a single commit.
- **Strict Boundary Preservation:** Each service retains its own isolated `pyproject.toml`, virtual environment, tests, and Dockerfile. No shared Python runtime dependencies between services.
- **Simplified Deployment & CI:** Unified Docker Compose build contexts and GitHub Actions pipelines.

### Negative / Tradeoffs
- Larger single repository clone size.
- Path-based triggers needed in CI to only test changed services.
