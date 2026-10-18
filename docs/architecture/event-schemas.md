# ReWearIt: Event Streaming, Topic Catalog & Kafka Topology

## 1. Authoritative Event Mapping Table

To ensure consistency across microservices, every message published to Kafka maps to an exact Protocol Buffer message type and unique `event_type` header string:

| Kafka Topic | Protobuf Message Type | `header.event_type` String | Producer Service | Primary Consumers | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `rewearit.items.events` | `ItemCreatedEvent` | `item.created` | `catalog-service` | `ai-worker`, `data-pipeline` | New apparel item created by seller |
| `rewearit.items.events` | `ItemStatusChangedEvent` | `item.status_changed` | `catalog-service` | `data-pipeline` | State change (`ACTIVE`, `RESERVED`, `SOLD`, `CANCELLED`) |
| `rewearit.ai.events` | `AIAppraisalCompletedEvent` | `ai.appraisal_completed` | `ai-worker` | `catalog-service`, `pricing-service` | VLM visual analysis, condition grade, 512-dim embedding |
| `rewearit.orders.events` | `OrderPlacedEvent` | `order.placed` | `order-service` | `catalog-service`, `data-pipeline` | Checkout initiated by buyer |
| `rewearit.orders.events` | `OrderEscrowLockedEvent` | `order.escrow_locked` | `order-service` | `catalog-service`, `data-pipeline` | Payment held in escrow; confirms reservation |
| `rewearit.orders.events` | `OrderCompletedEvent` | `order.completed` | `order-service` | `catalog-service`, `data-pipeline` | Order delivered; marks item `SOLD` |
| `rewearit.orders.events` | `OrderCancelledEvent` | `order.cancelled` | `order-service` | `catalog-service`, `data-pipeline` | Order timeout/cancelled; releases item reservation |
| `rewearit.orders.events` | `OrderRefundedEvent` | `order.refunded` | `order-service` | `data-pipeline` | Dispute settled with buyer refund |
| `rewearit.pricing.events`| `PricingValuationComputedEvent` | `pricing.valuation_computed` | `pricing-service` | `catalog-service` | Real-time fair market valuation computed |
| `rewearit.pricing.events`| `PriceDropAlertEvent` | `pricing.price_drop_alert` | `pricing-service` | `gateway` (Push/Notify) | ≥10% price reduction detected on active listing |
| `rewearit.analytics.pricing_metrics` | `PricingValuationComputedEvent` / Batch Schema | `analytics.pricing_metrics` | `data-pipeline` | `pricing-service` | Daily PySpark brand depreciation and demand curves |
| `rewearit.security.alerts` | SecurityAlertPayload | `security.bot_detected` | `data-pipeline` | `gateway` | Real-time bot or high-frequency abuse detection |
| `rewearit.telemetry.events`| `UserInteractionEvent` | `telemetry.user_interaction` | `gateway` | `data-pipeline` | High-volume user clicks, searches, and item views |

---

## 2. Topic Design & Partitioning Strategy

Kafka message keys guarantee that events for the same entity arrive strictly in order to consumer partitions.

| Topic Name | Message Key | Partitions (Local / Prod) | Retention | Compaction |
| :--- | :--- | :--- | :--- | :--- |
| `rewearit.items.events` | `item_id` | 3 / 12 | 7 days | No |
| `rewearit.ai.events` | `item_id` | 3 / 12 | 7 days | No |
| `rewearit.orders.events` | `order_id` | 3 / 12 | 30 days | No |
| `rewearit.pricing.events`| `item_id` | 3 / 6 | 3 days | No |
| `rewearit.analytics.pricing_metrics` | `brand` | 3 / 6 | 14 days | Yes (compacted) |
| `rewearit.security.alerts` | `client_ip` | 3 / 6 | 7 days | No |
| `rewearit.telemetry.events`| `session_id` | 6 / 24 | 48 hours | No |
| `rewearit.<topic>.retry` | Same as source | 3 / 6 | 3 days | No |
| `rewearit.dead_letter.queue`| `event_id` | 3 / 6 | 14 days | No |

---

## 3. Consumer Groups & Idempotency

### 3.1 Consumer Groups
- `cg-ai-workers`: Consumes `rewearit.items.events` for `item.created`. Scaled dynamically based on queue lag.
- `cg-catalog-syncer`: Consumes `rewearit.ai.events` and `rewearit.orders.events` to synchronize inventory states and visual embeddings into `pgvector`.
- `cg-pricing-engine`: Consumes `rewearit.ai.events` and `rewearit.analytics.pricing_metrics` to compute and cache fair market prices.
- `cg-spark-telemetry`: High-throughput Spark streaming consumer reading `rewearit.telemetry.events`.
- `cg-order-notifier`: Consumes `rewearit.orders.events` to dispatch user email/push simulated notifications.

### 3.2 Idempotency Contract
All consumers must implement Redis-backed deduplication before executing domain mutations:
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

## 4. Resilience, Retries & Dead-Letter Queues (DLQ)

When an event handler fails (e.g., third-party VLM API rate-limited):
1. **Exponential Backoff**: Up to 3 immediate retries with jitter (`1s`, `4s`, `16s`).
2. **Retry Topic**: If retries fail, publish to `rewearit.<topic>.retry` with a backoff header (`retry_count`).
3. **Dead-Letter Queue (DLQ)**: After 5 exhausted retries, publish to `rewearit.dead_letter.queue` including the full error stack trace and payload for manual replay or alerting.
