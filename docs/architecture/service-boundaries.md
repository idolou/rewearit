# ReWearIt: Service Boundaries & Domain Contracts

This document specifies the exact domain models, API interfaces, gRPC RPCs, and data stores for each microservice in the ReWearIt ecosystem.

---

## 1. `rewearit-gateway` (API Gateway & Auth Proxy)

- **Repository**: `idolou/rewearit-gateway`
- **Port**: `8000` (HTTP)
- **Framework**: FastAPI / Uvicorn (or Envoy proxy)
- **Storage**: Redis (Rate limiting & Token revocation)

### Responsibilities
1. **SSL Termination & Edge Routing**: Maps client requests (`/api/v1/items`, `/api/v1/orders`, etc.) to backend services via gRPC or internal HTTP.
2. **Authentication & Authorization**: Validates JWT bearer tokens, injects `X-User-ID`, `X-User-Email`, and `X-User-Roles` headers into downstream requests.
3. **Rate Limiting**: Sliding window rate limiting per IP / User ID using Redis (e.g. 100 req/min for unauthenticated, 1,000 req/min for authenticated).
4. **Telemetry Ingestion**: Receives client click/view beacons (`POST /api/v1/telemetry/events`) and immediately publishes `UserInteractionEvent` (`telemetry.user_interaction`) to the Kafka `rewearit.telemetry.events` topic.

---

## 2. `rewearit-catalog-service` (Inventory & Search)

- **Repository**: `idolou/rewearit-catalog-service`
- **Internal gRPC Port**: `50051`
- **REST Port**: `8001`
- **Database**: PostgreSQL 16 with `pgvector` extension

### Domain Entities
- **Item**:
  - `id`: UUID (Primary Key)
  - `seller_id`: UUID
  - `title`: String(255)
  - `description`: Text
  - `category`: Enum (`Tops`, `Bottoms`, `Outerwear`, `Footwear`, `Accessories`)
  - `brand`: String(100)
  - `size`: String(50)
  - `condition_grade`: `ConditionGrade` Enum (`NEW_WITH_TAGS`, `EXCELLENT`, `VERY_GOOD`, `GOOD`, `FAIR`)
  - `price`: Money (`currency`, `units`, `nanos`)
  - `status`: `ItemStatus` Enum (`DRAFT`, `ANALYZING`, `ACTIVE`, `RESERVED`, `SOLD`, `CANCELLED`)
  - `image_urls`: Array[String]
  - `embedding`: Vector(512) (Populated via `AIAppraisalCompletedEvent`)
  - `created_at`, `updated_at`: Timestamps

### gRPC Service Definition
```protobuf
syntax = "proto3";
package rewearit.catalog;

service CatalogService {
  rpc GetItem(GetItemRequest) returns (ItemResponse);
  rpc ReserveItem(ReserveItemRequest) returns (ReserveItemResponse);
  rpc ReleaseItem(ReleaseItemRequest) returns (ReleaseItemResponse);
  rpc MarkItemSold(MarkItemSoldRequest) returns (ItemResponse);
  rpc VisualSearch(VisualSearchRequest) returns (VisualSearchResponse);
}

message ReserveItemRequest {
  string item_id = 1;
  string order_id = 2;
  string buyer_id = 3;
}

message ReserveItemResponse {
  bool success = 1;
  string error_message = 2;
  int64 expires_at_timestamp = 3;
}
```
*(Canonical definition maintained in [`docs/schemas/catalog_service.proto`](../schemas/catalog_service.proto))*

### Concurrency & Reservation Guarantee (1-of-1 Garments)
Because second-hand inventory is strictly 1-of-1:
1. **Atomic Lock**: `ReserveItem` runs a single conditional transaction:
   ```sql
   UPDATE items
   SET status = 'RESERVED', reserved_until = NOW() + INTERVAL '15 minutes'
   WHERE id = :item_id AND (status = 'ACTIVE' OR (status = 'RESERVED' AND reserved_until < NOW()));
   ```
2. **Distributed Redis Key**: An associated Redis key `item:reservation:{item_id}` is set with `EX 900 NX` storing `{order_id}`.
3. **Reconciliation**:
   - **Lazy Release**: Query filters (`GetItem`, visual search) automatically treat items as `ACTIVE` if `status == 'RESERVED' AND reserved_until < NOW()`.
   - **Background Reaper**: A periodic task runs every 60 seconds resetting expired reservations whose orders never finalized.
- **Produces**:
  - `ItemCreatedEvent` (`item.created`) on `rewearit.items.events`
  - `ItemStatusChangedEvent` (`item.status_changed`) on `rewearit.items.events`
- **Consumes**:
  - `AIAppraisalCompletedEvent` (`ai.appraisal_completed`) from `rewearit.ai.events` to save 512-dim embedding and activate listing.
  - `OrderCompletedEvent` (`order.completed`) from `rewearit.orders.events` to finalize item as `SOLD`.
  - `OrderCancelledEvent` (`order.cancelled`) from `rewearit.orders.events` to release reservation back to `ACTIVE`.

---

## 3. `rewearit-order-service` (Orders & Escrow)

- **Repository**: `idolou/rewearit-order-service`
- **Internal gRPC Port**: `50052`
- **REST Port**: `8002`
- **Database**: PostgreSQL 16 (Strict ACID compliance)

### Order State Machine
```
[CREATED] ──(Payment Authorized)──> [ESCROW_HELD] ──(Shipped)──> [SHIPPED] ──(Delivered)──> [DELIVERED] ──(Confirmed)──> [COMPLETED]
    │                                     │                         │                                                    ▲
(Timeout)                             (Dispute)                 (Dispute)                                                │
    │                                     │                         │                                                    │
    ▼                                     ▼                         ▼                                                    │
[CANCELLED]                           [DISPUTED] ───────────────────────────────────────────────────────────(Resolved)────┘
```

### Domain Entities
- **Order**:
  - `id`: UUID (Primary Key)
  - `item_id`: UUID (Indexed)
  - `buyer_id`: UUID
  - `seller_id`: UUID
  - `amount`: Money (`currency`, `units`, `nanos`)
  - `escrow_fee`: Money (`currency`, `units`, `nanos`)
  - `status`: Enum (`CREATED`, `ESCROW_HELD`, `SHIPPED`, `DELIVERED`, `COMPLETED`, `CANCELLED`, `DISPUTED`)
  - `idempotency_key`: String(128) (Unique constraint to prevent double-charging)
  - `tracking_number`: String(100) (Optional)
  - `created_at`, `updated_at`: Timestamps

### Events Published (on `rewearit.orders.events`)
- `OrderPlacedEvent` (`order.placed`)
- `OrderEscrowLockedEvent` (`order.escrow_locked`)
- `OrderCompletedEvent` (`order.completed`)
- `OrderCancelledEvent` (`order.cancelled`)
- `OrderRefundedEvent` (`order.refunded`)

---

## 4. `rewearit-pricing-service` (Market Valuation & Trends)

- **Repository**: `idolou/rewearit-pricing-service`
- **Internal gRPC Port**: `50053`
- **REST Port**: `8003`
- **Database**: PostgreSQL 16 (Valuation curves) + Redis (Cache)

### Responsibilities
1. **Fair Market Value (FMV) Calculation**: Combines brand tier, category, condition score, and rolling market velocity to compute a recommended listing range `[low_price, target_price, high_price]`.
2. **Price Drop Detection**: Monitors item price modifications and checks if an item dropped by ≥10% from its historical average, publishing `PriceDropAlertEvent` (`pricing.price_drop_alert`).
3. **Analytics Ingestion**: Consumes pre-computed demand indices from Kafka topic `rewearit.analytics.pricing_metrics` produced by PySpark.
4. **Events Produced**: `PricingValuationComputedEvent` (`pricing.valuation_computed`), `PriceDropAlertEvent` (`pricing.price_drop_alert`).

---

## 5. `rewearit-ai-worker` (Multimodal Ingestion)

- **Repository**: `idolou/rewearit-ai-worker`
- **Execution Mode**: Continuous asynchronous consumer pool (Asyncio / Kafka Consumer)
- **External Dependencies**: Multimodal Vision-Language API / CLIP / S3

### Responsibilities
1. **Event Listening**: Consumes `rewearit.items.events` when `header.event_type == "item.created"`.
2. **Visual Inspection**:
   - Downloads garment images from S3/MinIO.
   - Extracts attributes: Brand logo OCR, fabric pattern (denim, wool, silk), clothing category, and wear flaws (stains, tears, fading).
   - Assigns a standardized `ConditionGrade` (`NEW_WITH_TAGS`, `EXCELLENT`, `VERY_GOOD`, `GOOD`, `FAIR`) with confidence score.
3. **Embedding Generation**: Produces a normalized 512-dimensional multimodal visual embedding.
4. **Publishing**: Emits `AIAppraisalCompletedEvent` (`ai.appraisal_completed`) to `rewearit.ai.events` (never connecting directly to Catalog database).

---

## 6. `rewearit-data-pipeline` (Big Data Streaming & Batch)

- **Repository**: `idolou/rewearit-data-pipeline`
- **Execution Mode**: PySpark Streaming + Scheduled Batch Cron
- **Storage**: S3 / MinIO Parquet Lakehouse + DuckDB / ClickHouse query layer

### Jobs:
1. **Clickstream Real-Time Stream**:
   - Consumes `rewearit.telemetry.events`.
   - Window: **15-minute sliding window with 5-minute slide and 2-minute late-data watermarking**.
   - Output: Real-time item popularity score and bot click frequency.
2. **Daily Market Price Depreciation Batch**:
   - Consumes historical `rewearit.orders.events` and `rewearit.items.events`.
   - Computes average resale price retention per brand (e.g., Patagonia retains 68% of MSRP vs Fast Fashion retaining 22%).
   - Stores Parquet tables in the data lake, and publishes summary metrics to `rewearit.analytics.pricing_metrics` for `pricing-service`.
