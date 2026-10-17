# Instructions for AI Coding Agents Building ReWearIt

Welcome, AI Agent. You are pair programming or autonomously contributing to the **ReWearIt** distributed platform. 

This repository (`rewearit`) is the **central architecture orchestrator, contract repository, and platform knowledge base**. Individual microservices, workers, and pipelines live in separate sibling repositories under the `idolou/` organization.

Follow these strict operating guidelines to ensure that your code modifications preserve architectural integrity, domain boundaries, and production resilience.

---

## 1. Prime Directives (Non-Negotiable Rules)

1. **Strict Domain Boundaries**:
   - **NEVER** write code in one service that connects directly to the database or internal storage of another service.
   - An Order Service must **never** do `SELECT * FROM items`. It must call the Catalog Service via gRPC or consume `item.*` Kafka events.
2. **Contract-First Evolution**:
   - All gRPC RPCs and Kafka event payloads must be defined in `docs/schemas/events.proto`.
   - If a feature requires new fields or a new event type, update the protobuf schema in this repository **first**, bump the version, and document the change in an Architecture Decision Record (`docs/adr/`).
3. **Idempotency Everywhere**:
   - Every Kafka consumer you write must check Redis or local transaction logs for duplicate message IDs before mutating state.
   - Every mutating POST endpoint (e.g., placing an order) must require and validate an `Idempotency-Key` header.
4. **100% Python Idioms**:
   - All services must use Python 3.12+, `asyncio`, type annotations on every function (`typing` / Pydantic v2), and pass `mypy --strict` and `ruff check`.
5. **Fail-Safe Asynchronous AI**:
   - Never invoke external LLM/VLM APIs directly within synchronous HTTP request lifecycles.
   - AI tasks must always be scheduled as asynchronous jobs consumed by `rewearit-ai-worker`.

---

## 2. Polyrepo Repository Map

When working on a specific subsystem, clone or navigate to its corresponding repository:

| Repository Name | Primary Tech | Role |
| :--- | :--- | :--- |
| `rewearit` (Current) | Markdown, Proto, Helm, Compose | Architecture docs, ADRs, schemas, K8s orchestration. |
| `rewearit-gateway` | FastAPI, Redis, Docker | Edge routing, JWT validation, rate limiting. |
| `rewearit-catalog-service` | FastAPI, gRPC, PostgreSQL, pgvector | Listings, inventory, visual search. |
| `rewearit-order-service` | FastAPI, gRPC, PostgreSQL, Redis | Orders, escrow state machine, idempotency. |
| `rewearit-pricing-service` | FastAPI, gRPC, PostgreSQL, Redis | Fair-market valuation algorithms. |
| `rewearit-ai-worker` | Python, VLM SDKs, Kafka, S3 | Garment attribute parsing, condition grading. |
| `rewearit-data-pipeline` | PySpark, Kafka, Parquet, DuckDB | Real-time clickstream streaming & batch analytics. |

---

## 3. Standard Service Directory Layout

Whenever you create or refactor a microservice in its dedicated repo, adhere to this clean structure:

```text
service-root/
├── app/
│   ├── api/                    # HTTP endpoints (FastAPI routers)
│   ├── grpc/                   # gRPC server implementations & generated stubs
│   ├── core/                   # Config, logging, telemetry, security
│   ├── domain/                 # Pure business logic, entities, value objects
│   ├── events/                 # Kafka producers, consumers, event schemas
│   ├── models/                 # SQLAlchemy / SQLModel / Pydantic models
│   └── services/               # Application services orchestrating domain logic
├── tests/
│   ├── unit/                   # Fast, mocked unit tests (Pytest)
│   ├── integration/            # Testcontainers / Docker-backed DB & Kafka tests
│   └── contract/               # Protobuf & schema compatibility tests
├── Dockerfile                  # Multi-stage non-root container build
├── pyproject.toml              # Dependencies & tool configs (Poetry / UV)
└── README.md                   # Service documentation & local running instructions
```

---

## 4. Verification Checklist Before Submitting Code

Before declaring any implementation task complete:
- [ ] **Linter & Formatting**: Run `ruff check .` and `ruff format .`.
- [ ] **Type Safety**: Run `mypy .` with zero errors.
- [ ] **Automated Tests**: Run `pytest tests/` with all assertions passing.
- [ ] **Docker Build**: Verify the container builds cleanly (`docker build -t <service>:local .`).
- [ ] **No Secrets**: Ensure no credentials, API keys, or private tokens are hardcoded. Use environment variables.
- [ ] **Schema Sync**: If event or RPC schemas changed, verify they match `docs/schemas/events.proto`.
