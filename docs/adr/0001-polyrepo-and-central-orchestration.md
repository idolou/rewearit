# ADR 0001: Polyrepo Strategy with Central Architecture & Orchestration Repository

- **Status**: Superseded by ADR 0006 (Monorepo Consolidation)
- **Date**: 2026-10-17
- **Deciders**: Ido Lourie

## Context
ReWearIt is an enterprise-grade distributed platform comprising several distinct services (API Gateway, Catalog, Orders, Pricing, AI Worker, Big Data Analytics). 

A key architectural question was whether to organize the codebase as a single monolithic repository (monorepo) or multiple independent repositories (polyrepo).

## Decision
We chose a **Polyrepo Strategy** anchored by a central architecture and orchestration repository (`rewearit`):
1. The central repository (`rewearit`) houses system design specs, protobuf event contracts, Kubernetes manifests, Helm umbrella charts, Docker Compose files for local mesh execution, and the AI agent knowledge base.
2. Each microservice and data pipeline component lives in its own dedicated GitHub repository under the `idolou/` namespace.

## Alternatives Considered
- **Single Monorepo (e.g., Pants / Nx / Turborepo)**:
  - *Why Rejected*: While convenient for atomic commits and code sharing, monorepos often lead to blurred boundary discipline in Python projects (e.g. accidental cross-service module imports). They also require complex CI path-filtering to avoid running heavyweight PySpark or AI tests on trivial gateway commits.
- **Pure Polyrepo without Central Orchestrator**:
  - *Why Rejected*: Fragmented schemas, ad-hoc Docker Compose setups per repo, and lack of an overarching system architecture view. Without a central repo, AI agents and engineers lack a single source of truth for event contracts and end-to-end local testing.

## Consequences
### Positive
- Strict dependency isolation: Each service maintains its own `pyproject.toml` and Docker image lifecycle.
- Independent CI/CD: Commits to the Catalog service do not trigger redundant builds or deployments of the Order service or PySpark pipeline.
- True representation of enterprise microservices boundaries.

### Negative / Tradeoffs
- Cross-repo schema synchronization requires maintaining Protobuf contracts in the central repository and publishing versioned Python client packages.
- Cross-cutting refactors that span multiple microservices require coordinated pull requests across separate repositories.
- Local multi-repo development requires cloning sibling repositories and managing multiple git worktrees simultaneously.
