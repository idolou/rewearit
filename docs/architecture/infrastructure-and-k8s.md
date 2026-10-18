# ReWearIt: Infrastructure, Kubernetes & Cloud Architecture

## 1. Local Development Topology (Docker Compose)

For local development, integration testing, and CI pipelines, the entire platform runs via Docker Compose with zero external cloud dependencies.

The authoritative configuration is maintained in:
👉 **[`deploy/docker-compose/docker-compose.yml`](../../deploy/docker-compose/docker-compose.yml)**

### Booting Local Infrastructure:
```bash
cd deploy/docker-compose
docker compose up -d
```

This provisions:
- **Redpanda (Kafka API)**: `localhost:9092`
- **Redpanda Console (Topic UI)**: `http://localhost:8080`
- **Redis (Cache & Distributed Locks)**: `localhost:6379`
- **MinIO (S3 Object Storage)**: `http://localhost:9000` (Console: `9001`)
- **PostgreSQL Databases**:
  - Catalog (`pgvector`): `localhost:5432` (`catalog_db`)
  - Orders: `localhost:5433` (`orders_db`)
  - Pricing: `localhost:5434` (`pricing_db`)

---

## 2. Kubernetes Architecture (Production & Staging)

### 2.1 Cluster & Namespace Strategy
We use **isolated EKS clusters per environment** (`rewearit-dev`, `rewearit-prod`). Within each cluster, workloads are strictly segmented into functional namespaces with dedicated RBAC and NetworkPolicies:

- `rewearit-system`: Ingress controllers (Nginx/Envoy), cert-manager, ExternalDNS.
- `rewearit-infra`: Kafka/Redpanda clusters, Redis Sentinel, MinIO / CSI storage drivers.
- `rewearit-services`: Stateless microservice deployments (`gateway`, `catalog`, `order`, `pricing`, `ai-worker`).
- `rewearit-analytics`: PySpark driver and executor pods running batch/streaming analytics.
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
- **Compute**: Amazon EKS running Kubernetes 1.30+ on managed EC2 node groups (`m6i.large` for general services, `g5.xlarge` GPU instances for local AI inference if needed).
- **Managed Data Services**:
  - AWS MSK (Managed Streaming for Apache Kafka) with IAM authentication.
  - Amazon Aurora Serverless v2 PostgreSQL with automated failover and `pgvector`.
  - Amazon S3 bucket with lifecycle policies transitioning raw images to Glacier after 90 days.
  - Amazon ElastiCache for Redis (Cluster mode enabled).
- **GitOps Continuous Delivery**: ArgoCD watching repository release tags and deploying Helm values to EKS namespaces.
