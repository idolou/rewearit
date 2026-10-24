# ReWearIt

Event-driven resale apparel commerce platform with multimodal AI appraisal, pgvector visual search, and atomic 1-of-1 garment reservations.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Docker Compose](https://img.shields.io/badge/docker--compose-v2-green.svg)](deploy/docker-compose/docker-compose.yml)
[![Kafka/Redpanda](https://img.shields.io/badge/streaming-Redpanda-red.svg)](https://redpanda.com/)
[![pgvector](https://img.shields.io/badge/database-pgvector-purple.svg)](https://github.com/pgvector/pgvector)
[![OpenTelemetry](https://img.shields.io/badge/observability-OpenTelemetry-orange.svg)](https://opentelemetry.io/)

---

## Architecture

ReWearIt is structured as a decoupled monorepo. Microservices communicate synchronously via gRPC for transactional operations and asynchronously over Kafka (Redpanda) for eventual consistency and domain events. Distributed traces are exported via OpenTelemetry to Jaeger.

```mermaid
flowchart TD
    classDef client fill:#e1f5fe,stroke:#0288d1,stroke-width:2px,color:#01579b;
    classDef service fill:#e8f5e9,stroke:#388e3c,stroke-width:2px,color:#1b5e20;
    classDef worker fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#4a148c;
    classDef db fill:#fff3e0,stroke:#f57c00,stroke-width:2px,color:#e65100;
    classDef stream fill:#ffebee,stroke:#d32f2f,stroke-width:2px,color:#b71c1c;
    classDef obs fill:#f5f5f5,stroke:#616161,stroke-width:2px,color:#212121;

    subgraph Clients["Clients"]
        client["Web / Mobile App"]:::client
    end

    subgraph Services["Core Microservices"]
        catalog["catalog-service<br/>REST :8001 | gRPC :50051"]:::service
        order["order-service<br/>REST :8003"]:::service
    end

    subgraph Workers["Async Workers"]
        ai["ai-worker<br/>Probes :8002<br/>VLM & 512-dim CLIP Embeddings"]:::worker
    end

    subgraph Storage["Storage & Caching (Isolated Ownership)"]
        db_catalog[("catalog_db<br/>PostgreSQL 16 + pgvector<br/>Port 5432")]:::db
        db_orders[("orders_db<br/>PostgreSQL 16<br/>Port 5433")]:::db
        redis[("Redis 7<br/>Idempotency & Locks<br/>Port 6379")]:::db
        minio[("MinIO S3<br/>Garment Media<br/>Port 9000/9001")]:::db
    end

    subgraph Messaging["Kafka Messaging (Redpanda :9092)"]
        t_items[["rewearit.items.events"]]:::stream
        t_ai[["rewearit.ai.events"]]:::stream
        t_orders[["rewearit.orders.events"]]:::stream
    end

    subgraph Observability["Distributed Tracing"]
        jaeger["Jaeger UI (:16686)<br/>OTLP Receiver (:4317)"]:::obs
    end

    %% Client Calls
    client -->|"POST /items"| catalog
    client -->|"POST /orders"| order

    %% Synchronous gRPC Reservation
    order -->|"gRPC ReserveItem<br/>(Atomic 1-of-1 Lock)"| catalog

    %% Storage access
    catalog --> db_catalog
    order --> db_orders
    order -.->|"Idempotency-Key Lock"| redis
    ai -->|"Read Image Assets"| minio

    %% Event Streams
    catalog -->|"item.created"| t_items
    t_items --> ai
    ai -->|"ai.appraisal_completed"| t_ai
    t_ai -->|"Activate & Embed"| catalog

    order -->|"order.placed<br/>order.completed"| t_orders
    t_orders -->|"Mark Item SOLD"| catalog

    %% Tracing
    catalog -.->|"OTLP Spans"| jaeger
    order -.->|"OTLP Spans"| jaeger
    ai -.->|"OTLP Spans"| jaeger
```

---

## 1-of-1 Garment Reservation & Escrow Flow

Second-hand garments are strictly unique (1-of-1 units). To prevent double-selling across concurrent checkouts, `order-service` acquires an atomic Redis idempotency lock, executes a synchronous gRPC reservation with row-level locks in `catalog-service`, and locks escrow funds before confirming the order.

```mermaid
sequenceDiagram
    autonumber
    actor Buyer
    participant OrderSvc as order-service (:8003)
    participant Redis as Redis (:6379)
    participant CatalogSvc as catalog-service (:50051)
    participant CatalogDB as catalog_db (PostgreSQL)
    participant Kafka as Redpanda (Kafka)

    Buyer->>OrderSvc: POST /api/v1/orders (Idempotency-Key, item_id)
    OrderSvc->>Redis: SETNX idemp:lock:<key> (Acquire Lock)
    OrderSvc->>CatalogSvc: gRPC ReserveItem(item_id, order_id, ttl=900s)
    CatalogSvc->>CatalogDB: SELECT ... FOR UPDATE WHERE id=item_id AND status='ACTIVE'
    
    alt Item Available
        CatalogDB-->>CatalogSvc: Row Locked (Active 1-of-1 Unit)
        CatalogSvc->>CatalogDB: UPDATE item SET status='RESERVED', reserved_by_order_id=order_id
        CatalogSvc-->>OrderSvc: ReserveItemResponse(success=True)
        OrderSvc->>OrderSvc: Create Order (Status: ESCROW_HELD)
        OrderSvc->>Kafka: Publish order.placed & order.escrow_locked
        OrderSvc-->>Buyer: 201 Created (Order in ESCROW_HELD)
    else Item Already Reserved or Sold
        CatalogDB-->>CatalogSvc: Row Unavailable / Reserved
        CatalogSvc-->>OrderSvc: ReserveItemResponse(success=False, error="ALREADY_RESERVED")
        OrderSvc->>Redis: DEL idemp:lock:<key>
        OrderSvc-->>Buyer: 409 Conflict ("Item is currently reserved")
    end
```

---

## Repository Structure

```text
rewearit/
├── contracts/                  # Canonical Protobuf & gRPC definitions
│   ├── catalog_service.proto   # gRPC reservation and visual search schema
│   └── events.proto            # Kafka event envelope and domain payloads
├── deploy/
│   └── docker-compose/         # Full multi-container mesh with healthchecks
│       └── docker-compose.yml
├── docs/                       # Architecture decisions (ADRs) & specs
│   ├── adr/
│   └── architecture/
└── services/                   # Independent microservices
    ├── catalog-service/        # Listings, pgvector visual search, gRPC servicer
    ├── ai-worker/              # Multimodal VLM appraisal & 512-dim visual embeddings
    └── order-service/          # Escrow state machine, Redis idempotency, gRPC client
```

---

## Services & Ports

| Service | Protocol / Port | Purpose |
| :--- | :--- | :--- |
| **`catalog-service`** | REST `:8001`, gRPC `:50051` | Garment catalog, pgvector vector search, gRPC inventory reservations |
| **`ai-worker`** | Health Probes `:8002` | Asynchronous Kafka worker: VLM attribute extraction & CLIP embeddings |
| **`order-service`** | REST `:8003` | Order transactions, Redis idempotency, escrow state machine |
| **`Jaeger UI`** | HTTP `:16686` (OTLP `:4317`) | Distributed tracing across HTTP, gRPC, and Kafka |
| **`Redpanda Console`** | HTTP `:8080` (Kafka `:9092`) | Kafka cluster management and topic inspection UI |
| **`MinIO Console`** | HTTP `:9001` (S3 `:9000`) | S3-compatible object storage for garment media |
| **`PostgreSQL Catalog`** | TCP `:5432` | Database for catalog service with `vector` extension |
| **`PostgreSQL Orders`** | TCP `:5433` | Database for order and escrow transactions |

---

## Quickstart

### Prerequisites
- Docker & Docker Compose v2+
- Python 3.12+ and [`uv`](https://github.com/astral-sh/uv) (for local testing)

### 1. Launch the Cluster
Run the entire platform with a single command:

```bash
docker compose -f deploy/docker-compose/docker-compose.yml up -d --build
```

Verify all containers are healthy:

```bash
docker compose -f deploy/docker-compose/docker-compose.yml ps
```

### 2. End-to-End Workflow Verification

#### Step 1: Create a Listing
```bash
curl -X POST http://localhost:8001/api/v1/items \
  -H "Content-Type: application/json" \
  -d '{
    "seller_id": "11111111-1111-1111-1111-111111111111",
    "title": "Vintage Levi'\''s 501 Denim Jacket",
    "description": "Authentic vintage trucker jacket in light wash denim",
    "category": "Outerwear",
    "brand": "Levi'\''s",
    "size": "L",
    "condition_grade": "EXCELLENT",
    "price_units": 145,
    "status": "ANALYZING",
    "image_urls": ["https://example.com/images/jacket.jpg"]
  }'
```
*The listing is created with status `ANALYZING`. `ai-worker` automatically consumes the event, grades condition, calculates a 512-dim embedding, and activates the listing (`ACTIVE`).*

#### Step 2: Checkout with Atomic Reservation
```bash
curl -X POST http://localhost:8003/api/v1/orders \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: order-run-001" \
  -d '{
    "item_id": "<ITEM_ID_FROM_STEP_1>",
    "seller_id": "11111111-1111-1111-1111-111111111111",
    "buyer_id": "22222222-2222-2222-2222-222222222222",
    "total_amount_units": 145,
    "currency": "USD"
  }'
```
*`order-service` invokes `catalog-service` via gRPC `ReserveItem`. The garment status becomes `RESERVED` and the order moves to `ESCROW_HELD`.*

#### Step 3: Complete Order & Release Escrow
```bash
curl -X POST http://localhost:8003/api/v1/orders/<ORDER_ID_FROM_STEP_2>/complete
```
*Order transitions to `COMPLETED`. An `order.completed` event is broadcast on Kafka, and `catalog-service` marks the garment as `SOLD`.*

---

## Observability

- **Distributed Traces (Jaeger):** Open [`http://localhost:16686`](http://localhost:16686) in your browser. Inspect end-to-end spans connecting HTTP requests, gRPC reservations, Kafka events, and database transactions.
- **Kafka Topics & Messages:** Open [`http://localhost:8080`](http://localhost:8080) for the Redpanda UI.

---

## Running Unit & Integration Tests

Each service contains isolated pytest suites:

```bash
# Catalog Service
cd services/catalog-service && uv run pytest

# AI Worker
cd services/ai-worker && uv run pytest

# Order Service
cd services/order-service && uv run pytest
```

---

## License
MIT
