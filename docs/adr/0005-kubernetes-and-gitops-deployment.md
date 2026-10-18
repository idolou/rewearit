# ADR 0005: Kubernetes, ArgoCD GitOps & Local Parity Architecture

- **Status**: Accepted
- **Date**: 2026-10-17
- **Deciders**: Ido Lourie

## Context
A major goal of the platform is demonstrating production-grade DevOps: containerization, Kubernetes orchestration, autoscaling, and cloud infrastructure on AWS. At the same time, local developer velocity must not require spending money on AWS resources during daily iteration, and deployments to cloud environments must follow declarative, auditable practices.

## Decision
1. **Container Standard**:
   - Every service is packaged with a multi-stage `Dockerfile` using `python:3.12-slim` and non-root security principles (`appuser:10001`).
2. **Local Parity via Docker Compose & k3d**:
   - `deploy/docker-compose/docker-compose.yml` spins up all shared infrastructure (Redpanda, Redis, MinIO, PostgreSQL instances) locally in under 10 seconds.
   - For Kubernetes verification, engineers can run lightweight **k3d** clusters locally before deploying to the cloud.
3. **Cloud Production (AWS EKS & Helm)**:
   - Deployments use an Umbrella Helm Chart structure with Horizontal Pod Autoscaling (HPA) targeting CPU, memory, and Kafka consumer lag metrics.
4. **GitOps Continuous Delivery via ArgoCD**:
   - Instead of running imperative `kubectl apply` commands in CI pipelines, **ArgoCD** is installed in the EKS cluster watching the `deploy/k8s/` directory in this central repository.
   - When GitHub Actions builds and tags a new container image in Amazon ECR, it updates the image tag in the central Helm `values.yaml`. ArgoCD detects the Git commit and reconciles the cluster state automatically.

## Alternatives Considered
- **Serverless (AWS Lambda + API Gateway + SQS)**:
  - *Why Rejected*: While serverless eliminates cluster management, it enforces restrictive execution timeouts, cold starts for Python/AI libraries, and makes running the entire distributed platform locally in Docker without cloud mock emulation (LocalStack) painful.
- **Imperative CI/CD (`kubectl apply` / `helm upgrade` in GitHub Actions)**:
  - *Why Rejected*: Pushing from CI requires opening long-lived cluster admin credentials to GitHub runners. GitOps via ArgoCD pulls declaratively from inside the cluster, prevents configuration drift, and provides an instant visual audit log of all running workloads.

## Consequences
### Positive
- Complete zero-cloud-cost local development loop with full feature parity.
- Cloud deployment manifests are tested, modular, declarative, and auditable via ArgoCD.
- Zero credentials needed on CI runners for cluster mutation.

### Negative / Tradeoffs
- Operating ArgoCD controllers, CRDs, and ingress endpoints introduces baseline Kubernetes cluster overhead and maintenance.
- Coordinated Helm chart updates for polyrepo services require a two-step workflow: first commit code in the service repo to build the ECR image, then commit the new image tag to the central umbrella Helm chart in `rewearit`.
- Local k3d/k8s testing requires higher RAM allocation on the host machine compared to bare Docker Compose.
