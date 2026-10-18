# ReWearIt: System Overview & Architecture Topology

## 1. High-Level Context (C4 Level 1 & 2)

ReWearIt is a distributed, event-driven commerce and analytics platform designed specifically for the dynamics of second-hand apparel.

```
                           [ Web / Mobile Clients ]
                                      │
                               (REST / JSON / JWT)
                                      ▼
                        ┌───────────────────────────┐
                        │     rewearit-gateway      │
                        │    (Port 8000 / Envoy)    │
                        └─────────────┬─────────────┘
                                      │
                   gRPC (HTTP/2 Internal Service Mesh)
        ┌─────────────────────────────┼─────────────────────────────┐
        ▼                             ▼                             ▼
┌───────────────┐             ┌───────────────┐             ┌───────────────┐
│catalog-service│             │ order-service │             │pricing-service│
│  (Port 50051) │             │  (Port 50052) │             │  (Port 50053) │
└───────┬───────┘             └───────┬───────┘             └───────┬───────┘
        │                             │                             │
   PostgreSQL                    PostgreSQL                    PostgreSQL
   + pgvector                     (Orders)                     + Redis Cache
  (Port 5432)                   (Port 5433)                    (Port 5434 / 6379)
        │                             │                             │
        └─────────────────────────────┼─────────────────────────────┘
                                      │
                         Kafka Event Bus (Port 9092)
                                      │
        ┌─────────────────────────────┴─────────────────────────────┐
        ▼                                                           ▼
┌───────────────┐                                           ┌───────────────┐
│   ai-worker   │                                           │ data-pipeline │
│ (Worker Pool) │                                           │(Spark Cluster)│
└───────┬───────┘                                           └───────┬───────┘
        │                                                           │
   VLM Engine                                                Parquet Lakehouse
 (Vision + Embeddings)                                        (MinIO / S3)
```

---

## 2. Core Architectural Pillars

### 2.1 Decoupled Microservices
- Each microservice owns its business domain completely (Database-per-Service). No cross-database joins are allowed.
- Internal synchronous communication (such as an Order verifying item availability with Catalog) is executed using high-performance **gRPC with Protobuf**.

### 2.2 Asynchronous Event Streaming
- State changes trigger domain events published to **Kafka/Redpanda**.
- Services consume events asynchronously, enabling loose coupling, backpressure handling, and eventual consistency.
- The transactional Outbox pattern ensures that database commits and event publication are atomic.

### 2.3 Applied Multimodal AI
- The `ai-worker` runs decoupled from the HTTP user request lifecycle.
- Ingests garment images asynchronously from S3/MinIO, parses visual attributes, assesses fabric wear, and produces dense vector embeddings for semantic similarity and recommendations.

### 2.4 Streaming Big Data Analytics
- Real-time clickstream events and transactions are ingested by Apache Spark (PySpark) Structured Streaming using **15-minute sliding windows with 5-minute slide and 2-minute late-data watermarking**.
- Computes rolling demand curves, price depreciation indices, and bot traffic flags, continuously updating the analytical lakehouse and pricing cache.

### 2.5 Cloud-Native Containerization & Kubernetes
- Fully containerized with multi-stage Docker builds.
- Deployed locally via Docker Compose or k3d Kubernetes, and to production via AWS EKS with Helm charts and automated GitHub Actions CI/CD.

---

## 3. End-to-End Happy Path Walkthroughs

### 3.1 Garment Listing & Asynchronous Multimodal Appraisal
1. **Listing Submission**: A seller uploads photos and rough item notes via `POST /api/v1/items` on `rewearit-gateway`.
2. **Catalog Creation**: Gateway routes the request to `rewearit-catalog-service`. Catalog persists the item in `catalog_db` with status `ANALYZING` and proposed price.
3. **Event Emitted**: Catalog service publishes `ItemCreatedEvent` (`item.created`) to Kafka topic `rewearit.items.events`.
4. **AI Worker Ingestion**: `rewearit-ai-worker` consumes `ItemCreatedEvent`, downloads photos from S3/MinIO, runs VLM visual attribute analysis and condition grading (`ConditionGrade`), and generates a 512-dim normalized visual embedding.
5. **Appraisal Published**: AI Worker publishes `AIAppraisalCompletedEvent` (`ai.appraisal_completed`) to `rewearit.ai.events`.
6. **Catalog Update**: Catalog service consumes `AIAppraisalCompletedEvent`, writes the 512-dim embedding to its `pgvector` index, updates detected brand/condition attributes, and promotes item status to `ACTIVE`.
7. **Pricing Calibration**: Concurrently, `rewearit-pricing-service` consumes `AIAppraisalCompletedEvent`, calculates the fair-market valuation range, and emits `PricingValuationComputedEvent` (`pricing.valuation_computed`).

### 3.2 Visual Search & Purchase with Escrow Reservation
1. **Interactive Visual Search**: A buyer uploads an inspiration photo or text query via `POST /api/v1/search/visual`.
2. **In-Process Query Vector**: `catalog-service` passes the query through its embedded lightweight ONNX/CLIP model (<30ms) to compute a 512-dim query vector, executing an indexed cosine distance query (`<=>`) in PostgreSQL `pgvector` to return top matching active items.
3. **Checkout Initiation**: Buyer initiates purchase via `POST /api/v1/orders`.
4. **Synchronous Inventory Lock**: `rewearit-order-service` calls `ReserveItem` on `catalog-service` via internal gRPC. Catalog locks the item with a 15-minute TTL (`RESERVED`) in Redis/PostgreSQL.
5. **Escrow Locked**: Order service authorizes payment, transitions order status to `ESCROW_HELD`, and publishes `OrderEscrowLockedEvent` (`order.escrow_locked`) to Kafka `rewearit.orders.events`.
6. **Delivery & Completion**: Upon confirmed parcel delivery, Order service marks order `COMPLETED`, releases seller payout, and publishes `OrderCompletedEvent` (`order.completed`).
7. **Permanent Inventory Finalization**: Catalog service consumes `OrderCompletedEvent` and marks item permanently `SOLD`.
