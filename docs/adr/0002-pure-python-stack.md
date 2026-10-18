# ADR 0002: Uniform 100% Python Architecture

- **Status**: Accepted
- **Date**: 2026-10-17
- **Deciders**: Ido Lourie

## Context
In distributed systems, microservices can technically be written in heterogeneous languages (e.g. Go for gateway, Java for orders, Python for data). However, multi-language stacks increase developer cognitive overhead, complicate shared schema generation, and fragment test tooling.

## Decision
We chose **100% Python (Python 3.12+)** across the entire platform:
- **Microservices & API Gateway**: **FastAPI** with `asyncio`, Uvicorn, and `pydantic-v2`.
- **Inter-service RPC**: **gRPC Python** with `grpcio-tools`.
- **Big Data & Analytics**: **Apache Spark (PySpark)** for both streaming and batch jobs.
- **AI & Multimodal**: Native Python with modern vision-language SDKs and CLIP.

## Alternatives Considered
- **Polyglot Go (Gateway & Orders) + Python (Data & AI)**:
  - *Why Rejected*: While Go provides exceptional raw throughput and minimal binary footprint for the Gateway, managing dual language toolchains (Go toolchain + Python virtualenvs, linters, Docker bases, and Protobuf stub generators) doubles engineering overhead for a solo developer or lean team.
- **Node.js / TypeScript + Python**:
  - *Why Rejected*: Splitting between TypeScript and Python forces dual type validation systems (Zod/TypeScript vs. Pydantic/Python) without offering substantial compute advantages over async Python.

## Consequences
### Positive
- Unified developer velocity, code reuse, and seamless integration between transactional services, PySpark data engineering, and AI models.
- Consistent type safety with Pydantic and Mypy across every service.
- Frictionless pair programming with AI coding agents who excel at modern idiomatic Python.

### Negative / Tradeoffs
- Higher memory footprint per container instance compared to statically compiled Go binaries (~80-120MB baseline for Uvicorn vs. ~15MB for Go).
- CPU-bound serialization (e.g., heavy JSON parsing or custom cryptographic operations) requires careful offloading to thread pools or C-extensions (`uvloop`, `orjson`, Pydantic core in Rust) to avoid starving the `asyncio` event loop.
- PySpark introduces JVM interop overhead (Py4J) compared to native Scala Spark, requiring disciplined tuning of executor memory.
