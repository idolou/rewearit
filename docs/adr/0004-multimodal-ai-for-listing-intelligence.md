# ADR 0004: Asynchronous Multimodal AI Ingestion & pgvector Storage

- **Status**: Accepted
- **Date**: 2026-10-17
- **Deciders**: Ido Lourie

## Context
Second-hand garments arrive with unstandardized user descriptions and photos. The platform needs to classify apparel, evaluate physical condition, and enable visual similarity search while respecting strict microservice isolation and avoiding blocking web requests.

## Decision
1. **Asynchronous Decoupled Ingestion**:
   - The user upload emits an `ItemCreatedEvent` (`item.created`) with photo S3 keys.
   - The `rewearit-ai-worker` processes photos via vision-language models (VLM) in the background.
   - AI Worker never connects directly to the Catalog database. Instead, it emits `AIAppraisalCompletedEvent` (`ai.appraisal_completed`) containing metadata and visual embeddings to Kafka `rewearit.ai.events`.
2. **Vector Store Ownership**:
   - The `catalog-service` hosts the vector index internally using **PostgreSQL with `pgvector`**, keeping the inventory relational attributes and vector embeddings co-located within a single ACID-compliant store.
3. **Dual-Model Inference Strategy**:
   - Heavy VLM evaluation (wear appraisal, brand recognition) runs asynchronously in background workers.
   - Real-time interactive search queries generate text/image embeddings in-process inside `catalog-service` using lightweight ONNX/CLIP models (<30ms latency on standard CPU).

## Alternatives Considered
- **Dedicated Standalone Vector DB (Qdrant / Pinecone / Milvus)**:
  - *Why Rejected*: While standalone vector databases offer specialized indexing features at multi-million scale, they introduce a separate stateful cluster, distributed transaction synchronizations, and foreign-key drift between relational item metadata and vector point IDs. PostgreSQL + `pgvector` co-locates relational filters (`WHERE category = 'Tops' AND price < 50`) with cosine vector distance in a single ACID query.
- **Synchronous VLM Calls in HTTP Handlers**:
  - *Why Rejected*: Vision-language model calls take 1.5 to 6+ seconds. Executing them inside the seller listing HTTP request handler leads to client gateway timeouts, high connection concurrency, and cascading failure during upstream provider rate limits.

## Consequences
### Positive
- Fully preserves microservice data ownership (Anti-Goal 2.3.1).
- Eliminates the operational complexity of managing a separate standalone Qdrant cluster for initial iterations.
- Sub-second search response times without async polling roundtrips.

### Negative / Tradeoffs
- PostgreSQL `pgvector` requires dedicated index tuning (`ivfflat` vs `hnsw`) and memory allocation (`maintenance_work_mem`) as catalog scale exceeds 500,000 vectors.
- Reliance on external commercial VLMs introduces token billing costs and upstream rate-limit failure modes requiring robust exponential backoff.
- Multi-model embedding consistency: Changing or fine-tuning the query CLIP model requires batch re-embedding of the entire catalog to prevent vector space divergence.
