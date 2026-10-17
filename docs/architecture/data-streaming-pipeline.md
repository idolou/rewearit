# ReWearIt: Big Data & Streaming Pipeline Architecture

## 1. Engine & Storage Topology

The `rewearit-data-pipeline` processes two distinct workloads:
1. **Real-time Event Streaming**: Low-latency (sub-second to 1-minute micro-batches) consumption of user interactions and order states via **Apache Spark Structured Streaming**.
2. **Scheduled Batch Analytics**: Daily batch jobs computing brand market valuation indexes, seller reliability scores, and category velocity trends.

```
                  ┌──────────────────────────────────────────────┐
                  │ Kafka Topics (Items, Orders, Telemetry, etc) │
                  └──────────────────────┬───────────────────────┘
                                         │
                                (PySpark Streaming)
                                         ▼
                        ┌─────────────────────────────────┐
                        │ Spark Structured Streaming Core │
                        │  - Sliding Windows (10 min)     │
                        │  - Watermarking (2 min)         │
                        │  - Anomaly & Fraud Filtering    │
                        └────────┬───────────────┬────────┘
                                 │               │
                     (Hot Metrics / Redis)       (Raw Lakehouse Sink / S3)
                                 ▼               ▼
                        ┌────────────────┐ ┌───────────────────────────┐
                        │  Redis Hot KV  │ │ Parquet Lakehouse (S3)    │
                        │ (Fast Lookup)  │ │ (Partitioned: year/mo/day)│
                        └────────────────┘ └─────────────┬─────────────┘
                                                         │
                                                  (Daily PySpark Batch)
                                                         ▼
                                           ┌───────────────────────────┐
                                           │ Brand Depreciation Curves │
                                           │ & Price Elasticity Matrix │
                                           └───────────────────────────┘
```

---

## 2. Real-Time Streaming Workloads

### Job 1: Clickstream Ingestion & Trending Items Index
- **Input Topic**: `rewearit.telemetry.events`
- **Windowing**: 15-minute sliding window with 5-minute slide and 2-minute late-data watermark:
  ```python
  windowed_views = (
      telemetry_stream
      .withWatermark("timestamp", "2 minutes")
      .groupBy(
          window("timestamp", "15 minutes", "5 minutes"),
          col("target_item_id")
      )
      .count()
      .withColumnRenamed("count", "recent_view_count")
  )
  ```
- **Hot Sink**: Writes rolling top-viewed items directly to Redis sorted sets (`ZADD trending_items <count> <item_id>`) for real-time recommendation feeds.

### Job 2: Bot & Fraud Detection Engine
- Aggregates request rates per IP/User session:
  - If views > 120 per minute or order attempts > 5 per minute with card failure:
  - Emits security alert to Kafka `rewearit.security.alerts` and adds IP to Redis blacklist for `rewearit-gateway` to reject immediately.

---

## 3. Batch Analytics & Lakehouse Architecture

### Parquet Table Schema: `fact_marketplace_sales`
Partitioned by `sale_year`, `sale_month`:
- `order_id`: String
- `item_id`: String
- `category`: String
- `brand`: String
- `condition_grade`: String
- `original_list_price`: Double
- `final_sale_price`: Double
- `days_to_sell`: Integer
- `seller_rating`: Double

### Batch Output: Brand Depreciation Index
Spark batch runs daily to calculate the **Resale Retention Percentage (RRP)**:
$$\text{RRP}_{\text{brand, condition}} = \frac{\sum \text{final\_sale\_price}}{\sum \text{original\_msrp}} \times 100$$
This metric is published directly to `rewearit-pricing-service` to maintain automated valuation models.
