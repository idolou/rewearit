# ReWearIt: AI Multimodal Processing Pipeline

## 1. Pipeline Overview

The `rewearit-ai-worker` is a critical differentiator in the ReWearIt ecosystem. It eliminates the manual friction of second-hand selling by automatically extracting attributes, grading wear and tear, and indexing the visual style of apparel from user-uploaded photos.

```
[ User Uploads Photos ] ──> S3 / MinIO ──> [ ItemCreatedEvent (item.created) ]
                                                   │
                                                   ▼
                                       ┌───────────────────────┐
                                       │  rewearit-ai-worker   │
                                       └───────────┬───────────┘
                                                   │
                         ┌─────────────────────────┴─────────────────────────┐
                         ▼                                                   ▼
             ┌───────────────────────┐                           ┌───────────────────────┐
             │  VLM Vision Analysis  │                           │ Embedding Generation  │
             │ (Claude 3.5 / GPT-4o) │                           │  (CLIP / OpenCLIP)    │
             └───────────┬───────────┘                           └───────────┬───────────┘
                         │                                                   │
             [ Structured Metadata ]                             [ 512-dim Dense Vector ]
             (Brand, Category, Grade, FMV)                                   │
                         │                                                   ▼
                         └─────────────────────────┬─────────────────────────┘
                                                   ▼
                           [ AIAppraisalCompletedEvent (ai.appraisal_completed) ]
                                                   │
                                                   ▼
                                [ Consumed by rewearit-catalog-service ]
                                                   │
                                                   ▼
                                    [ Written to pgvector Index ]
```

---

## 2. Multi-Stage Ingestion Pipeline

### Stage 1: Image Pre-processing & Sanitation
- Download original image from S3.
- Standardize size to 1024x1024, strip EXIF GPS metadata, convert to WebP for optimized storage.

### Stage 2: Vision-Language Attribute Extraction
The worker invokes a structured VLM call with strict JSON schema enforcement referencing canonical `ConditionGrade`:

```json
{
  "category": "Outerwear",
  "subcategory": "Denim Jacket",
  "brand": "Levi's",
  "confidence_brand": 0.94,
  "materials": ["100% Cotton", "Denim"],
  "primary_color": "Faded Blue",
  "condition_assessment": {
    "grade": "VERY_GOOD",
    "flaws_detected": [
      {"type": "slight fraying", "location": "cuff", "severity": "minor"}
    ],
    "wear_indicators": "Light wash fading consistent with gentle wear",
    "confidence_grade": 0.89
  },
  "suggested_tags": ["vintage", "streetwear", "90s", "denim", "distressed"],
  "authenticity_risk_score": 0.05
}
```

### Stage 3: Multimodal Vector Embedding
- Passes garment crops through a vision encoder (CLIP `ViT-B/32` or `ViT-L/14`) to produce a 512-dimensional vector.
- Normalizes the embedding with L2-norm for cosine similarity searches:
  $$\text{sim}(u, v) = \frac{u \cdot v}{\|u\| \|v\|}$$

### Stage 4: Visual Similarity Search Execution
The `catalog-service` consumes `AIAppraisalCompletedEvent`, writes the embedding, and uses PostgreSQL's `pgvector` HNSW index (supporting incremental ingestion from row 0 without pre-training):
```sql
CREATE INDEX idx_items_embedding_hnsw ON items USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- Query: Find visually similar clothing
SELECT id, title, price, 1 - (embedding <=> :target_embedding) AS similarity
FROM items
WHERE status = 'ACTIVE'
ORDER BY embedding <=> :target_embedding
LIMIT 12;
```

---

## 3. Evaluation & Guardrails
- **Cost Optimization**: Cache image embeddings by SHA-256 image hashes in Redis to avoid re-running identical photos.
- **Circuit Breakers**: If the primary VLM provider exceeds 5% error rates or latency > 4,000ms, fallback to an open-source local model or stub classifier to prevent queue starvation.
