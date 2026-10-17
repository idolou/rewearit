# ADR 0003: Event-Driven Architecture with Kafka & Redpanda

- **Status**: Accepted
- **Date**: 2026-10-17
- **Deciders**: Ido Lourie

## Context
State changes across second-hand commerce (new listings, AI attribute grading, inventory reservation, order escrow transitions, price fluctuations) require loose coupling and asynchronous scalability without synchronous cascading failures.

## Decision
We adopted an **Event-Driven Architecture (EDA)** powered by **Apache Kafka APIs**:
1. In production, we deploy **Amazon MSK** or a dedicated multi-broker Kafka cluster on AWS EKS.
2. In local development and automated CI, we utilize **Redpanda**—a C++-based, Kafka-compatible streaming platform that boots in sub-second time with zero JVM overhead and identical client libraries.
3. Every state change publishes an immutable domain event conforming to the canonical Protobuf envelope defined in `docs/schemas/events.proto`.

## Consequences
### Positive
- Guaranteed partitioning order by entity ID (e.g. `item_id`, `order_id`).
- High-throughput replayability for analytical consumers (PySpark) without burdening transactional relational databases.
- Backpressure resistance: AI worker and PySpark pipelines consume at their own rate without blocking client checkout requests.

### Negative / Tradeoffs
- Requires handling eventual consistency, deduplication, and consumer group rebalances.
