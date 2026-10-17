# ADR 0001: Polyrepo Strategy with Central Architecture & Orchestration Repository

- **Status**: Accepted
- **Date**: 2026-10-17
- **Deciders**: Ido Lourie

## Context
ReWearIt is an enterprise-grade distributed platform comprising several distinct services (API Gateway, Catalog, Orders, Pricing, AI Worker, Big Data Analytics). 

A key architectural question was whether to organize the codebase as a single monolithic repository (monorepo) or multiple independent repositories (polyrepo).

## Decision
We chose a **Polyrepo Strategy** anchored by a central architecture and orchestration repository (`rewearit`):
1. The central repository (`rewearit`) houses system design specs, protobuf event contracts, Kubernetes manifests, Helm umbrella charts, Docker Compose files for local mesh execution, and the AI agent knowledge base.
2. Each microservice and data pipeline component lives in its own dedicated GitHub repository under the `idolou/` namespace.

## Consequences
### Positive
- Strict dependency isolation: Each service maintains its own `pyproject.toml` and Docker image lifecycle.
- Independent CI/CD: Commits to the Catalog service do not trigger redundant builds or deployments of the Order service or PySpark pipeline.
- True representation of enterprise microservices boundaries.

### Negative / Tradeoffs
- Cross-repo schema synchronization requires maintaining Protobuf contracts in the central repository and publishing versioned Python client packages.
