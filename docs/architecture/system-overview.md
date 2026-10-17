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
- Real-time clickstream events and transactions are ingested by Apache Spark (PySpark) Streaming.
- Computes rolling demand curves, price depreciation indices, and bot traffic flags, continuously updating the analytical lakehouse and pricing cache.

### 2.5 Cloud-Native Containerization & Kubernetes
- Fully containerized with multi-stage Docker builds.
- Deployed locally via Docker Compose or k3d Kubernetes, and to production via AWS EKS with Helm charts and automated GitHub Actions CI/CD.
