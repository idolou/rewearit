# ADR 0004: Asynchronous Multimodal AI Ingestion & pgvector Storage

- **Status**: Accepted
- **Date**: 2026-10-17
- **Deciders**: Ido Lourie

## Context
Second-hand garments arrive with unstandardized user descriptions and photos. The platform needs to classify apparel, evaluate physical condition, and enable visual similarity search while respecting strict microservice isolation and avoiding blocking web requests.

## Decision
1. **Asynchronous Decoupled Ingestion**:
   - The user upload emits an `item.created` event with photo S3 keys.
   - The `rewearit-ai-worker` processes photos via vision-language models (VLM) in the background.
   - AI Worker never connects directly to the Catalog database. Instead, it emits `item.ai_appraised` containing metadata and visual embeddings to Kafka.
2. **Vector Store Ownership**:
   - The `catalog-service` hosts the vector index internally using **PostgreSQL with `pgvector`**, keeping the inventory relational attributes and vector embeddings co-located within a single ACID-compliant store.
3. **Dual-Model Inference Strategy**:
   - Heavy VLM evaluation (wear appraisal, brand recognition) runs asynchronously in background workers.
   - Real-time interactive search queries generate text/image embeddings in-process inside `catalog-service` using lightweight ONNX/CLIP models (<30ms latency on standard CPU).

## Consequences
### Positive
- Fully preserves microservice data ownership (Anti-Goal 2.3.1).
- Eliminates the operational complexity of managing a separate standalone Qdrant cluster for initial iterations.
- Sub-second search response times without async polling roundtrips.

### Negative / Tradeoffs
- PostgreSQL `pgvector` requires index tuning (`ivfflat` vs `hnsw`) as dataset size exceeds 500,000 vectors.
