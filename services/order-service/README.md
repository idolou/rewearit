# ReWearIt Order Service (`rewearit-order-service`)

Microservice responsible for managing orders, checkout transactions, escrow state machine transitions, and atomic 1-of-1 garment reservations.

## Key Capabilities
- **Atomic Garment Reservation:** gRPC client to `catalog-service:50051` (`ReserveItem`) ensuring garments cannot be double-sold.
- **Idempotency Protection:** Redis atomic `SET NX EX` on `Idempotency-Key` header with TTL caching.
- **Escrow State Machine:** Tracks order states `CREATED -> ESCROW_HELD -> SHIPPED -> DELIVERED -> COMPLETED` (or `CANCELLED` / `REFUNDED`).
- **Kafka Event Streaming:** Publishes `order.placed`, `order.escrow_locked`, `order.completed`, `order.cancelled` to `rewearit.orders.events`.
- **Distributed Tracing:** Full OpenTelemetry instrumentation propagating W3C trace contexts across REST, gRPC, and Kafka to Jaeger.
