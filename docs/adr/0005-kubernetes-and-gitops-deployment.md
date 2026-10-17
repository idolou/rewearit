# ADR 0005: Kubernetes, GitOps & Local Parity Architecture

- **Status**: Accepted
- **Date**: 2026-10-17
- **Deciders**: Ido Lourie

## Context
A major goal of the platform is demonstrating production-grade DevOps: containerization, Kubernetes orchestration, autoscaling, and cloud infrastructure on AWS. At the same time, local developer velocity must not require spending money on AWS resources during daily iteration.

## Decision
1. **Container Standard**:
   - Every service is packaged with multi-stage `Dockerfile` using `python:3.12-slim` and non-root security principles (`appuser`).
2. **Local Parity via Docker Compose & k3d**:
   - `deploy/docker-compose/docker-compose.yml` spins up all shared infrastructure (Redpanda, Redis, MinIO, PostgreSQL instances) locally in under 10 seconds.
   - For Kubernetes verification, engineers can run lightweight **k3d** clusters locally before pushing to cloud.
3. **Cloud Production (AWS EKS & Helm)**:
   - Deployments use an Umbrella Helm Chart structure with Horizontal Pod Autoscaling (HPA) targeting CPU, memory, and Kafka consumer lag metrics.
   - GitHub Actions pipelines handle automated testing, container image building, and pushing to Amazon ECR.

## Consequences
### Positive
- Complete zero-cloud-cost local development loop with full feature parity.
- Cloud deployment manifests are tested, modular, and ready for AWS EKS.
