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

## Alternatives Considered
- **Traditional Message Queues (RabbitMQ / AWS SQS + SNS)**:
  - *Why Rejected*: SQS and RabbitMQ excel at work queues where messages are deleted once acknowledged. However, they lack durable distributed commit logs, making replayability for PySpark stream processing and historical backfilling difficult or impossible without re-architecting data ingestion.
- **Redis Pub/Sub or Redis Streams**:
  - *Why Rejected*: Redis Pub/Sub provides no persistence guarantees (at-most-once delivery). Redis Streams offers log-based streaming but lacks the enterprise partitioning, compaction, consumer ecosystem, and native Apache Spark connector maturity that Kafka provides.

## Consequences
### Positive
- Guaranteed partitioning order by entity ID (e.g. `item_id`, `order_id`).
- High-throughput replayability for analytical consumers (PySpark) without burdening transactional relational databases.
- Backpressure resistance: AI worker and PySpark pipelines consume at their own rate without blocking client checkout requests.

### Negative / Tradeoffs
- Requires handling eventual consistency: downstream consumers must tolerate delayed state updates and implement strict deduplication via idempotency keys.
- Operational complexity of Kafka partition management, retention policies, and consumer group rebalances during pod deployments or network partitions.
- Local development without Redpanda (e.g., standard Apache Kafka with ZooKeeper or KRaft) can be resource-heavy on developer laptops (>2GB RAM).
