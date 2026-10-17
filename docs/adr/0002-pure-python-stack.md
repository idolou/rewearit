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

## Consequences
### Positive
- Unified developer velocity, code reuse, and seamless integration between transactional services, PySpark data engineering, and AI models.
- Consistent type safety with Pydantic and Mypy.
- Frictionless pair programming with AI coding agents who excel at modern idiomatic Python.

### Negative / Tradeoffs
- Python services require multi-worker asynchronous event loops (Uvicorn / uvloop) to achieve high I/O concurrency compared to native compiled Go binaries.
