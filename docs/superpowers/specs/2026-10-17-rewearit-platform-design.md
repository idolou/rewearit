# ReWearIt Platform: Distributed Architecture & System Design

- **Project Name**: ReWearIt
- **Date**: 2026-10-17
- **Author**: Ido Lourie
- **Status**: Proposed
- **Repository Type**: Central Platform Orchestrator & Knowledge Base (Polyrepo Root)
- **Primary Stack**: 100% Python (FastAPI, PySpark, Pydantic, gRPC, LangGraph/VLM), Kafka/Redpanda, Kubernetes, AWS

---

## 1. Intent & Executive Summary

### 1.1 The "Why"
Second-hand apparel marketplaces face high-throughput, asymmetric data challenges: unique 1-of-1 inventory units, subjective condition grading, high return rates, and rapid price depreciation. 

**ReWearIt** is an event-driven distributed resale commerce platform designed to solve these operational challenges using decoupled microservices, asynchronous multimodal AI appraisals, visual similarity search (pgvector), and atomic transactional inventory reservations.

---

## 2. Goals, Non-Goals & Anti-Goals

### 2.1 Goals
1. **Domain-Driven Microservices**: Clean separation of concerns across business domains (Catalog, Orders/Escrow, Dynamic Pricing, User/Auth) implemented in asynchronous Python (FastAPI) communicating synchronously via gRPC and asynchronously via Kafka.
2. **Asynchronous Multimodal AI Pipeline**: Automated item ingestion where uploaded garment images and notes are processed by vision-language models to extract brand, category, condition grading, and visual embeddings for semantic vector search.
3. **Big Data & Event Streaming**: Real-time market event ingestion (item listings, price updates, user views, order transactions) via Kafka/Redpanda, processed with Apache Spark (PySpark) to compute dynamic price indices, demand trends, and fraud/anomaly detection.
4. **Cloud-Native & DevOps Excellence**: Production-grade Docker multi-stage builds, Kubernetes (manifests & Helm charts) with Horizontal Pod Autoscaling (HPA), local mesh execution via Docker Compose/k3d, and automated GitHub Actions CI/CD deploying to AWS (EKS, RDS, S3, MSK).
5. **Polyrepo Architecture with Central Knowledge Base**: Independent git repositories for each service, coordinated by this central repository containing shared contract schemas (Protobuf), orchestration charts, architectural decision records (ADRs), and agent guidance docs.

### 2.2 Non-Goals
1. **Complex Consumer UI**: Building a polished frontend React/Next.js/mobile app is explicitly a non-goal. An interactive API documentation portal (Swagger/OpenAPI), Postman/Newman collections, and a lightweight Streamlit/FastAPI test dashboard are sufficient.
2. **Real Payment Provider Integration**: Integrating live Stripe/PayPal production merchant accounts is not required. The Order Service simulates escrow and payment lifecycle transitions idempotently using industry-standard state machines.
3. **Third-Party Logistics APIs**: Physical courier label generation and warehouse robotics are mocked via event webhooks.

### 2.3 Anti-Goals (Failure Modes)
1. **The "Monolith in Disguise"**: Avoid microservices that share a single unified relational database or rely on distributed ACID two-phase commits. Each service owns its private data store.
2. **Naive AI API Wrapper**: Avoid synchronous, blocking calls to external LLMs inside HTTP request handlers. All AI processing must be decoupled into asynchronous background workers using message queues with retry, backoff, and dead-letter queues (DLQ).
3. **Over-Engineered Monorepo**: Do not force all services into a tightly coupled monorepo. Services must have isolated dependency trees, independent test suites, and individual deployment lifecycles.

---

## 3. System Constraints & Decisions

### 3.1 Architectural Principles
- **Language Uniformity**: **100% Python** across all services and jobs (Python 3.12+), utilizing `asyncio`, FastAPI, Pydantic v2, PySpark, and gRPC.
- **Polyrepo Strategy**: Individual GitHub repositories per service, tied together via Git submodules or external versioned contract packages.
- **Contract-First Communication**: Internal RPCs and Kafka event payloads are defined strictly with Protocol Buffers (`.proto`) and Pydantic schemas maintained in this central repository.
- **Eventual Consistency**: State across services is synchronized asynchronously using event publishing following the Outbox Pattern where transactional reliability is essential.
- **Local Dev Parity**: The entire platform must spin up locally with a single command (`docker compose up` or `k3d cluster create`) with zero external cloud dependencies required for local testing.

---

## 4. Architectural Overview & Service Boundaries

```
                         [ External Clients / Gateway ]
                                       │
                              (HTTPS / REST / JWT)
                                       ▼
                             ┌───────────────────┐
                             │  rewearit-gateway │ (FastAPI / Envoy)
                             └─────────┬─────────┘
                                       │ (gRPC Internal Mesh)
                ┌──────────────────────┼──────────────────────┐
                ▼                      ▼                      ▼
      ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
      │ rewearit-catalog │   │  rewearit-order  │   │ rewearit-pricing │
      │     service      │   │     service      │   │     service      │
      └─────────┬────────┘   └─────────┬────────┘   └─────────┬────────┘
                │                      │                      │
         (PostgreSQL +                 │ (PostgreSQL)         │ (Redis +
           pgvector)                   │                      │  PostgreSQL)
                │                      │                      │
                └──────────────────────┼──────────────────────┘
                                       │
                            Events (Kafka / Redpanda)
                                       │
                ┌──────────────────────┴──────────────────────┐
                ▼                                             ▼
      ┌──────────────────┐                          ┌──────────────────┐
      │  rewearit-ai-    │                          │ rewearit-data-   │
      │  worker-service  │                          │ pipeline (Spark) │
      └─────────┬────────┘                          └─────────┬────────┘
                │                                             │
         (VLM / Qdrant /                               (Parquet Lakehouse /
          pgvector Sink)                                DuckDB Analytics)
```

### 4.1 Service Breakdown

#### 1. `rewearit-gateway` (API Gateway & Auth Proxy)
- **Role**: Edge entry point for client requests.
- **Responsibilities**:
  - Request routing, rate-limiting (Redis token bucket), and SSL termination.
  - JWT token verification and user context injection (`X-User-ID`, `X-User-Roles`).
  - Aggregating frontend composite requests.

#### 2. `rewearit-catalog-service` (Inventory, Search & Vector Store)
- **Role**: Core domain service managing apparel items, categories, and inventory state.
- **Responsibilities**:
  - CRUD operations on clothing listings (title, brand, size, color, condition, price, seller ID).
  - Synchronous gRPC API for order validation and inventory reservation with a 15-minute reservation TTL.
  - Consumes `AIAppraisalCompletedEvent` (`ai.appraisal_completed`) from Kafka to update listing attributes and write visual embeddings to its own PostgreSQL `pgvector` store (preserving database-per-service isolation).
  - In-process lightweight ONNX/CLIP query embedding generation for interactive real-time visual and semantic search (<30ms latency on CPU), distinguishing fast query embeddings from heavy background VLM appraisals.
  - Emits: `item.created`, `item.status_changed`.
  - Storage: Dedicated PostgreSQL database with `pgvector` extension.

#### 3. `rewearit-order-service` (Transactions & Escrow)
- **Role**: Financial lifecycle and order state management.
- **Responsibilities**:
  - Initiates synchronous gRPC `ReserveItem` call to `catalog-service` during checkout creation. If successful, creates order in `ESCROW_HELD`.
  - Manages order state machine: `CREATED` -> `ESCROW_HELD` -> `SHIPPED` -> `DELIVERED` -> `COMPLETED` (or `CANCELLED` / `REFUNDED`).
  - Guarantees idempotency via unique client transaction keys stored in Redis.
  - Emits asynchronous events on `rewearit.orders.events`: `order.placed`, `order.escrow_locked`, `order.completed`, `order.cancelled`, `order.refunded`.
  - Storage: Dedicated PostgreSQL database with strict transactional isolation.

#### 4. `rewearit-pricing-service` (Market Value & Price Discovery)
- **Role**: Dynamic pricing suggestions and price change tracking.
- **Responsibilities**:
  - Computes fair-market valuation for garments based on historical sales, brand tier, and condition grade.
  - Consumes analytical metrics published by `rewearit-data-pipeline` via Kafka topic `rewearit.analytics.pricing_metrics` and caches valuation curves in Redis/PostgreSQL.
  - Exposes gRPC endpoint for real-time price recommendations.
  - Emits: `pricing.valuation_computed`, `pricing.price_drop_alert`.
  - Storage: Redis for low-latency cached valuations + PostgreSQL for historical price curves.

#### 5. `rewearit-ai-worker-service` (Multimodal Ingestion & Verification)
- **Role**: Asynchronous intelligence processor for listing automation.
- **Responsibilities**:
  - Consumes `item.created` events with image URLs from S3/MinIO.
  - Invokes vision-language models (e.g. Claude 3.5 Sonnet / GPT-4o / local VLM) to:
    - Detect garment type (e.g. "Vintage Denim Jacket").
    - Recognize brand tags and authenticity indicators.
    - Grade physical condition according to `ConditionGrade` (`NEW_WITH_TAGS`, `EXCELLENT`, `VERY_GOOD`, `GOOD`, `FAIR`).
    - Generate 512-dimensional multimodal visual embeddings.
  - Emits: `AIAppraisalCompletedEvent` (`ai.appraisal_completed`) on `rewearit.ai.events` containing all parsed metadata and visual embeddings to Kafka (never writing directly to Catalog database).

#### 6. `rewearit-data-pipeline` (Big Data & Streaming Analytics)
- **Role**: High-throughput distributed data processing using Apache Spark (PySpark).
- **Responsibilities**:
  - **Streaming Pipeline**: Consumes continuous event streams (`item.viewed`, `item.searched`, `order.completed`) from Kafka to compute rolling demand indices and detect bot activity.
  - **Batch Pipeline**: Daily PySpark batch jobs calculating brand depreciation curves and category sales velocity.
  - **Serving Interface**: Emits aggregated pricing metrics to Kafka topic `rewearit.analytics.pricing_metrics` for `pricing-service` consumption, while persisting raw fact tables in Parquet lakehouse on S3/MinIO.

---

## 5. Event Streaming Contracts (Kafka Topics)

All events are formatted with standard envelope metadata and JSON/Avro payloads:

| Topic Name | Producer | Primary Consumers | Purpose |
| :--- | :--- | :--- | :--- |
| `rewearit.items.events` | `catalog-service` | `ai-worker`, `data-pipeline` | Informs workers of new listings or modifications. |
| `rewearit.ai.events` | `ai-worker` | `catalog-service`, `pricing-service` | Publishes AI-derived attributes and condition scores. |
| `rewearit.orders.events` | `order-service` | `catalog-service`, `data-pipeline` | Drives inventory reservation and sales analytics. |
| `rewearit.pricing.events`| `pricing-service`| `catalog-service` | Sends price adjustment suggestions and alerts. |
| `rewearit.analytics.pricing_metrics`| `data-pipeline` | `pricing-service` | Publishes daily brand depreciation & demand indices. |
| `rewearit.telemetry.events`| `gateway` | `data-pipeline` | High-volume user clicks, search queries, and views. |

---

## 6. Infrastructure, Kubernetes & Deployment Architecture

### 6.1 Containerization (Docker)
- Multi-stage `Dockerfile` per service utilizing `python:3.12-slim`.
- Dedicated non-root user (`appuser:10001`).
- Virtual environment caching and minimal runtime image size (< 150MB).

### 6.2 Kubernetes Deployment Specs
- **Cluster & Namespace Strategy**: Dedicated EKS cluster per environment (`rewearit-dev`, `rewearit-prod`). Within each cluster, namespaces are segmented functionally: `rewearit-system` (Ingress/cert-manager), `rewearit-infra` (Kafka/Redis/DBs), `rewearit-services` (Stateless microservices), `rewearit-analytics` (PySpark), and `rewearit-monitoring`.
- **Deployments**: Stateless FastAPI microservices with readiness and liveness probes (`/healthz`, `/ready`).
- **Horizontal Pod Autoscaler (HPA)**: CPU and memory-based autoscaling targets (50-80% thresholds).
- **Stateful Infrastructure**: Kafka/Redpanda, PostgreSQL, Redis, and MinIO managed via Helm charts or dedicated operators.
- **Config & Secrets**: Kubernetes ConfigMaps for environment settings and Secrets for API tokens and database credentials.

### 6.3 Cloud Infrastructure Blueprint (AWS)
- **Compute**: Amazon EKS (Elastic Kubernetes Service) managed node groups.
- **Storage**: Amazon S3 for garment image storage and analytics Parquet lakehouse.
- **Database**: Amazon Aurora Serverless v2 (PostgreSQL) with `pgvector`.
- **Streaming**: Amazon MSK (Managed Streaming for Apache Kafka) or self-hosted Redpanda on EKS.
- **Caching**: Amazon ElastiCache (Redis).
- **CI/CD**: GitHub Actions workflows building images, running test gates, pushing to Amazon ECR, and deploying to EKS.

---

## 7. AI Agent Knowledge Base Design

To empower future AI agents (and human engineers) to continuously develop, test, and maintain this system without architectural drift, the repository includes a standardized knowledge base:

```text
rewearit/
├── docs/
│   ├── superpowers/specs/      # Primary engineering design specs
│   ├── architecture/           # Deep-dive system blueprints & C4 diagrams
│   ├── adr/                    # Architecture Decision Records (Numbered ADRs)
│   ├── schemas/                # Shared Protocol Buffer (.proto) & Pydantic definitions
│   └── agent-instructions/     # Explicit operating rules for AI coding agents
```

### Agent Rules (`docs/agent-instructions/AGENTS.md`)
1. **Never Violate Service Boundaries**: An agent working on the Order Service must NEVER access the Catalog Service database directly.
2. **Contract-First Changes**: Any change to an event payload or gRPC RPC must first be updated in `docs/schemas/`, accompanied by a new ADR.
3. **Idempotency & Resilience**: All event handlers written by agents must implement idempotent consumer logic with Redis deduping.
4. **Verification Gate**: Every pull request or service commit must include passing unit tests and contract validation tests (`pytest`).

---

## 8. What is Left to the Builder

The following operational implementation details are delegated to the implementer/builder during active development:
1. **VLM Model Selection**: Selecting between Claude 3.5 Sonnet, GPT-4o-mini, or open-source CLIP for initial development cost vs. accuracy tradeoffs.
2. **Local Kafka Distribution**: Utilizing Redpanda vs. Apache Kafka for local Docker Compose development (Redpanda is recommended for near-zero startup time and lower RAM usage).
3. **Spark Cluster Sizing**: Local Spark standalone mode configuration vs. Dockerized Spark master/worker nodes for running PySpark batch analytics.
4. **Synthetic Data Seeding**: Building an automated generator to seed the Catalog and Kafka streams with 10,000+ realistic apparel items and user click events for realistic benchmarking.
