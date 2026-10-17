# ReWearIt: Event Streaming & Kafka Topology

## 1. Topic Design & Partitioning Strategy

Kafka message keys must guarantee that events for the same entity arrive in order to consumer partitions.

| Topic Name | Message Key | Partitions (Local / Prod) | Retention | Compaction |
| :--- | :--- | :--- | :--- | :--- |
| `rewearit.items.events` | `item_id` | 3 / 12 | 7 days | No |
| `rewearit.ai.events` | `item_id` | 3 / 12 | 7 days | No |
| `rewearit.orders.events` | `order_id` | 3 / 12 | 30 days | No |
| `rewearit.pricing.events`| `item_id` | 3 / 6 | 3 days | No |
| `rewearit.telemetry.events`| `session_id` | 6 / 24 | 48 hours | No |
| `rewearit.dead_letter.queue`| `event_id` | 3 / 6 | 14 days | No |

---

## 2. Consumer Groups & Idempotency

### 2.1 Consumer Groups
- `cg-ai-workers`: Consumes `rewearit.items.events`. Scaled up/down based on image backlog queue depth.
- `cg-catalog-syncer`: Consumes `rewearit.ai.events` and `rewearit.orders.events` to update listing status and embeddings.
- `cg-spark-telemetry`: High-throughput Spark streaming consumer group reading `rewearit.telemetry.events`.
- `cg-order-notifier`: Consumes `rewearit.orders.events` to dispatch push/email simulated notifications.

### 2.2 Idempotency Contract
All consumers must implement Redis-backed deduplication before processing:
```python
async def process_event(event: EventEnvelope):
    dedup_key = f"idempotency:{event.header.event_id}"
    is_new = await redis.set(dedup_key, "1", ex=86400, nx=True)
    if not is_new:
        logger.info(f"Duplicate event ignored: {event.header.event_id}")
        return
    
    # Execute domain logic
    await handle_domain_logic(event)
```

---

## 3. Resilience, Retries & Dead-Letter Queues (DLQ)

When an event handler fails (e.g., third-party VLM API rate-limited):
1. **Exponential Backoff**: Up to 3 immediate retries with jitter (`1s`, `4s`, `16s`).
2. **Retry Topic**: If retries fail, publish to `rewearit.<topic>.retry` with a backoff header.
3. **Dead-Letter Queue (DLQ)**: After 5 exhausted retries, publish to `rewearit.dead_letter.queue` including the full error stack trace and payload for manual replay or alerting.
