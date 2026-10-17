# ReWearIt: Infrastructure, Kubernetes & Cloud Architecture

## 1. Local Development Topology (Docker Compose)

For local development and continuous testing, the entire platform runs via Docker Compose with zero external cloud dependencies.

```yaml
version: "3.9"

services:
  # --- Message Broker ---
  redpanda:
    image: docker.redpanda.com/redpandadata/redpanda:v24.1.2
    container_name: rewearit-redpanda
    ports:
      - "9092:9092"
      - "9644:9644"
    command:
      - redpanda start
      - --smp 1
      - --memory 1G
      - --overprovisioned
      - --kafka-addr internal://0.0.0.0:9092,external://0.0.0.0:9092

  # --- Caching & Hot Storage ---
  redis:
    image: redis:7.2-alpine
    container_name: rewearit-redis
    ports:
      - "6379:6379"

  # --- Object Storage (S3 Emulation) ---
  minio:
    image: minio/minio:RELEASE.2024-05-01T01-11-10Z
    container_name: rewearit-minio
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadminpassword
    command: server /data --console-address ":9001"

  # --- Databases ---
  postgres-catalog:
    image: pgvector/pgvector:pg16
    container_name: rewearit-postgres-catalog
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: catalog_db
      POSTGRES_USER: catalog_user
      POSTGRES_PASSWORD: catalog_password

  postgres-orders:
    image: postgres:16-alpine
    container_name: rewearit-postgres-orders
    ports:
      - "5433:5432"
    environment:
      POSTGRES_DB: orders_db
      POSTGRES_USER: orders_user
      POSTGRES_PASSWORD: orders_password

  postgres-pricing:
    image: postgres:16-alpine
    container_name: rewearit-postgres-pricing
    ports:
      - "5434:5432"
    environment:
      POSTGRES_DB: pricing_db
      POSTGRES_USER: pricing_user
      POSTGRES_PASSWORD: pricing_password
```

---

## 2. Kubernetes Architecture (Production & Staging)

### 2.1 Cluster Structure (Namespaces)
- `rewearit-system`: Ingress controllers (Nginx/Envoy), cert-manager, ExternalDNS.
- `rewearit-infra`: Kafka/Redpanda clusters, Redis Sentinel, MinIO / CSI storage drivers.
- `rewearit-services`: Stateless microservice deployments (`gateway`, `catalog`, `order`, `pricing`, `ai-worker`).
- `rewearit-analytics`: PySpark driver and executor pods.
- `rewearit-monitoring`: Prometheus, Grafana, OpenTelemetry Collector, Tempo.

### 2.2 Helm Chart Architecture
```text
deploy/k8s/
├── helm/
│   ├── rewearit-umbrella/      # Umbrella chart coordinating all sub-charts
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   └── requirements.yaml
│   ├── charts/
│   │   ├── gateway/
│   │   ├── catalog-service/
│   │   ├── order-service/
│   │   ├── pricing-service/
│   │   ├── ai-worker/
│   │   └── spark-jobs/
```

### 2.3 Horizontal Pod Autoscaling (HPA) Policy
- **Gateway & Catalog**: Min: 2, Max: 10, Target CPU: 70%, Target Memory: 75%.
- **AI Worker**: Scales dynamically based on Kafka consumer lag metrics exported via Prometheus (`kafka_consumergroup_lag > 50` spins up additional worker pods up to 20 replicas).

---

## 3. Cloud Infrastructure Blueprint (AWS EKS)

- **VPC & Networking**: Multi-AZ VPC across 3 Availability Zones with public and private subnets, NAT Gateways, and strict Security Groups.
- **Compute**: Amazon EKS running Kubernetes 1.30+ on managed EC2 node groups (e.g. `m6i.large` for general services, `g5.xlarge` GPU instances for local AI inference if needed).
- **Managed Data Services**:
  - AWS MSK (Managed Streaming for Apache Kafka) with IAM authentication.
  - Amazon Aurora Serverless v2 PostgreSQL with automated failover and pgvector.
  - Amazon S3 bucket with lifecycle policies transitioning raw images to Glacier after 90 days.
  - Amazon ElastiCache for Redis (Cluster mode enabled).
