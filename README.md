# ReWearIt: Distributed Resale Commerce & Intelligence Platform

> **Central Architecture, Contract Orchestrator & Knowledge Base**

[![Architecture: Microservices](https://img.shields.io/badge/Architecture-Event--Driven%20Microservices-blue)](./docs/architecture/system-overview.md)
[![Language: 100% Python](https://img.shields.io/badge/Language-100%25%20Python%203.12-brightgreen)](./docs/adr/0002-pure-python-stack.md)
[![Event Streaming: Kafka / Redpanda](https://img.shields.io/badge/Streaming-Kafka%20%2F%20Redpanda-red)](./docs/architecture/event-schemas.md)
[![Big Data: PySpark](https://img.shields.io/badge/Big%20Data-Apache%20Spark-orange)](./docs/architecture/data-streaming-pipeline.md)
[![AI: Multimodal VLM + pgvector](https://img.shields.io/badge/AI-Multimodal%20VLM%20%2B%20pgvector-purple)](./docs/architecture/ai-multimodal-pipeline.md)
[![Cloud & Infra: K8s / AWS](https://img.shields.io/badge/Infra-Kubernetes%20%2F%20AWS%20EKS-lightblue)](./docs/architecture/infrastructure-and-k8s.md)

---

## 📖 Overview

**ReWearIt** is an enterprise-grade distributed platform designed to solve the high-throughput, asymmetric data challenges of second-hand apparel marketplaces (inspired by platforms like Vinted, StockX, and Depop).

Rather than a simple monolithic storefront, ReWearIt is built as a suite of decoupled, domain-driven microservices connected via Kafka event streams, powered by an asynchronous multimodal AI appraisal engine, and backed by a PySpark big data analytics pipeline.

This repository serves as the **central architecture orchestrator, schema repository, and living knowledge base** for the entire ReWearIt ecosystem.

---

## 🏛️ System Architecture Topology

```mermaid
flowchart TD
    classDef client fill:#e1f5fe,stroke:#0288d1,stroke-width:2px,color:#01579b;
    classDef gateway fill:#e8eaf6,stroke:#3f51b5,stroke-width:2px,color:#1a237e;
    classDef service fill:#e8f5e9,stroke:#388e3c,stroke-width:2px,color:#1b5e20;
    classDef worker fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#4a148c;
    classDef db fill:#fff3e0,stroke:#f57c00,stroke-width:2px,color:#e65100;
    classDef stream fill:#ffebee,stroke:#d32f2f,stroke-width:2px,color:#b71c1c;
    classDef obs fill:#f5f5f5,stroke:#616161,stroke-width:2px,color:#212121;

    subgraph Clients["Clients & Edge Gateway"]
        web["Web & Mobile Apps"]:::client
        gateway["rewearit-gateway<br/>FastAPI / Reverse Proxy<br/>Port 8000"]:::gateway
    end

    subgraph CoreServices["Domain Microservices (Python 3.12 + FastAPI + gRPC)"]
        catalog["rewearit-catalog-service<br/>REST :8001 | gRPC :50051"]:::service
        orders["rewearit-order-service<br/>REST :8003 | gRPC :50052"]:::service
        pricing["rewearit-pricing-service<br/>REST :8004 | gRPC :50053"]:::service
    end

    subgraph AsyncWorkers["Intelligence & Analytics Workers"]
        ai_worker["rewearit-ai-worker<br/>Probes :8002<br/>VLM + 512-dim Embeddings"]:::worker
        data_pipeline["rewearit-data-pipeline<br/>PySpark Streaming & Lakehouse"]:::worker
    end

    subgraph StorageMesh["Isolated Storage & Caching Layer"]
        db_catalog[("catalog_db<br/>PostgreSQL 16 + pgvector<br/>Port 5432")]:::db
        db_orders[("orders_db<br/>PostgreSQL 16<br/>Port 5433")]:::db
        db_pricing[("pricing_db<br/>PostgreSQL 16<br/>Port 5434")]:::db
        redis[("Redis 7<br/>Cache & Idempotency<br/>Port 6379")]:::db
        minio[("MinIO S3 Storage<br/>Garments & Lakehouse<br/>Port 9000/9001")]:::db
    end

    subgraph KafkaMesh["Event Streaming Mesh (Redpanda / Kafka API :9092)"]
        t_items[["rewearit.items.events"]]:::stream
        t_ai[["rewearit.ai.events"]]:::stream
        t_orders[["rewearit.orders.events"]]:::stream
        t_pricing[["rewearit.pricing.events"]]:::stream
    end

    subgraph ObservabilityMesh["Distributed Visibility & Tracing"]
        jaeger["Jaeger Distributed Tracing<br/>UI :16686 | OTLP :4317/:4318"]:::obs
        console["Redpanda Console<br/>Kafka UI :8080"]:::obs
    end

    %% Client and Gateway Routing
    web -->|"REST / HTTPS"| gateway
    gateway -->|"HTTP / REST"| catalog
    gateway -->|"HTTP / REST"| orders
    gateway -->|"HTTP / REST"| pricing

    %% Synchronous Inter-Service gRPC Mesh
    orders -->|"gRPC ReserveItem<br/>(Atomic 1-of-1 Lock)"| catalog
    orders -->|"gRPC GetValuation"| pricing

    %% Service Database Ownership (Strict Domain Boundaries)
    catalog -->|"Read / Write"| db_catalog
    orders -->|"Read / Write"| db_orders
    pricing -->|"Read / Write"| db_pricing

    %% Caching & Shared Objects
    catalog -.->|"Cache Embedding"| redis
    orders -.->|"Idempotency-Key Lock"| redis
    ai_worker -.->|"SHA-256 Appraisal Cache"| redis
    ai_worker -->|"Fetch Garment Photos"| minio
    data_pipeline -->|"Parquet Lakehouse"| minio

    %% Event Streaming Mesh (Pub/Sub)
    catalog -->|"item.created"| t_items
    t_items -->|"Consume"| ai_worker
    ai_worker -->|"ai.appraisal_completed"| t_ai
    t_ai -->|"Activate & Embed"| catalog
    t_ai -->|"Valuation Baseline"| pricing

    orders -->|"order.placed<br/>order.completed"| t_orders
    t_orders -->|"Mark Item SOLD"| catalog
    t_orders -->|"Sales Velocity"| data_pipeline

    %% Distributed Tracing
    catalog -.->|"OTLP Spans"| jaeger
    orders -.->|"OTLP Spans"| jaeger
    ai_worker -.->|"OTLP Spans"| jaeger
    pricing -.->|"OTLP Spans"| jaeger
```

---

## ⚡ 1-of-1 Secondhand Garment Reservation & Escrow Flow

```mermaid
sequenceDiagram
    autonumber
    actor Buyer
    participant Gateway as rewearit-gateway
    participant OrderSvc as rewearit-order-service
    participant Redis as Redis (Idempotency)
    participant CatalogSvc as rewearit-catalog-service
    participant CatalogDB as catalog_db (PostgreSQL)
    participant Kafka as Redpanda (Kafka)
    participant AIWorker as rewearit-ai-worker

    Note over Buyer, AIWorker: Phase 1: Listing Creation & AI Appraisal
    Buyer->>CatalogSvc: POST /api/v1/items (Listing with Photo URL)
    CatalogSvc->>CatalogDB: INSERT item (Status: ANALYZING)
    CatalogSvc->>Kafka: Publish item.created (rewearit.items.events)
    Kafka->>AIWorker: Consume item.created
    AIWorker->>AIWorker: Strip EXIF, VLM Appraisal, 512-dim Embedding
    AIWorker->>Kafka: Publish ai.appraisal_completed (rewearit.ai.events)
    Kafka->>CatalogSvc: Consume ai.appraisal_completed
    CatalogSvc->>CatalogDB: UPDATE item SET status='ACTIVE', embedding=vec, condition='GOOD'

    Note over Buyer, AIWorker: Phase 2: Atomic Checkout & 1-of-1 Garment Reservation
    Buyer->>Gateway: POST /api/v1/orders (Idempotency-Key, item_id)
    Gateway->>OrderSvc: Forward Checkout Request
    OrderSvc->>Redis: SETNX idempotency:order:<key> (Lock)
    OrderSvc->>CatalogSvc: gRPC ReserveItem(item_id, order_id, ttl=900s)
    CatalogSvc->>CatalogDB: SELECT ... FOR UPDATE WHERE id=item_id AND status='ACTIVE'
    alt Item Available
        CatalogDB-->>CatalogSvc: Row Locked (1-of-1 Available)
        CatalogSvc->>CatalogDB: UPDATE item SET status='RESERVED', order_id=order_id
        CatalogSvc-->>OrderSvc: ReserveItemResponse(success=True)
        OrderSvc->>OrderSvc: Transition Order Status to ESCROW_HELD
        OrderSvc->>Kafka: Publish order.placed & order.escrow_locked (rewearit.orders.events)
        OrderSvc-->>Gateway: 201 Created (Order in ESCROW_HELD)
        Gateway-->>Buyer: 201 Order Confirmed (Escrow Secured)
    else Item Already Reserved or Sold (Race Condition)
        CatalogDB-->>CatalogSvc: Row Unavailable / Reserved
        CatalogSvc-->>OrderSvc: ReserveItemResponse(success=False, error="ALREADY_RESERVED")
        OrderSvc-->>Gateway: 409 Conflict ("Garment already reserved")
        Gateway-->>Buyer: 409 Conflict
    end
```

---

## 📚 Knowledge Base & Design Docs

- **[Master System Design Specification](./docs/superpowers/specs/2026-10-17-rewearit-platform-design.md)**: Exhaustive technical blueprint covering intent, goals, constraints, domain models, and execution boundaries.
- **[System Architecture & C4 Topology](./docs/architecture/system-overview.md)**: High-level architectural context and container models.
- **[Service Boundaries & Contracts](./docs/architecture/service-boundaries.md)**: Microservice APIs, database schemas, and domain responsibilities.
- **[Event Streaming & Kafka Contracts](./docs/architecture/event-schemas.md)**: Topic partitioning, consumer groups, and idempotency guarantees.
- **[Protobuf Event Schemas (`events.proto`)](./docs/schemas/events.proto)**: Canonical message envelope and payload definitions.
- **[AI Multimodal Pipeline](./docs/architecture/ai-multimodal-pipeline.md)**: VLM image analysis, condition grading, and pgvector similarity search.
- **[Big Data & Streaming Pipeline](./docs/architecture/data-streaming-pipeline.md)**: PySpark streaming windows and daily market depreciation batch models.
- **[Infrastructure & Kubernetes Blueprint](./docs/architecture/infrastructure-and-k8s.md)**: Docker multi-stage builds, Helm charts, and AWS EKS topology.
- **[AI Agent Development Directives (`AGENTS.md`)](./docs/agent-instructions/AGENTS.md)**: Standards, domain rules, and verification checklist for AI coding agents.

### Architecture Decision Records (ADRs)
- **[ADR 0001: Polyrepo Strategy with Central Orchestration](./docs/adr/0001-polyrepo-and-central-orchestration.md)**
- **[ADR 0002: 100% Python Unified Stack](./docs/adr/0002-pure-python-stack.md)**
- **[ADR 0003: Event-Driven Architecture with Kafka & Redpanda](./docs/adr/0003-event-driven-messaging-with-kafka.md)**
- **[ADR 0004: Asynchronous Multimodal AI & pgvector Ownership](./docs/adr/0004-multimodal-ai-for-listing-intelligence.md)**
- **[ADR 0005: Kubernetes, ArgoCD GitOps & Local Parity](./docs/adr/0005-kubernetes-and-gitops-deployment.md)**

---

## 🚀 Quickstart: Bootstrapping Local Infrastructure

The platform provides a complete local shared infrastructure mesh via Docker Compose with zero external cloud dependencies:

```bash
# Navigate to docker compose folder
cd deploy/docker-compose

# Spin up Redpanda (Kafka), Redpanda Console, Redis, MinIO (S3), and 3 PostgreSQL DBs
docker compose up -d
```

### Local Services & Dashboards
| Service | Local Endpoint | Purpose | Credentials |
| :--- | :--- | :--- | :--- |
| **Redpanda Console** | `http://localhost:8080` | Kafka Topic & Consumer UI | None |
| **MinIO Console** | `http://localhost:9001` | S3 Object Storage UI | `minioadmin` / `minioadminpassword` |
| **Kafka Broker** | `localhost:9092` | Event Ingestion & Streaming | None |
| **Redis** | `localhost:6379` | Caching & Idempotency Locks | None |
| **PostgreSQL Catalog** | `localhost:5432` | Inventory & `pgvector` store | `catalog_user` / `catalog_password` |
| **PostgreSQL Orders** | `localhost:5433` | Order State & Escrow | `orders_user` / `orders_password` |
| **PostgreSQL Pricing** | `localhost:5434` | Valuation Curves | `pricing_user` / `pricing_password` |

---

## 📦 Sibling Microservices Repositories

| Repository | Tech Stack | Description |
| :--- | :--- | :--- |
| **`rewearit`** | Markdown, Proto, Helm, Compose | *You are here.* Central architecture & orchestrator. |
| **`rewearit-gateway`** | FastAPI, Redis, Docker | Edge API gateway, JWT auth, rate limiting. |
| **`rewearit-catalog-service`** | FastAPI, gRPC, PostgreSQL, pgvector | Inventory listings, visual similarity search. |
| **`rewearit-order-service`** | FastAPI, gRPC, PostgreSQL, Redis | Escrow state machine, order idempotency. |
| **`rewearit-pricing-service`** | FastAPI, gRPC, PostgreSQL, Redis | Real-time fair market value calculation. |
| **`rewearit-ai-worker`** | Python, VLM SDKs, Kafka, S3 | Multimodal clothing categorization & condition grading. |
| **`rewearit-data-pipeline`** | PySpark, Kafka, Parquet, DuckDB | Clickstream streaming & market analytics batch jobs. |
