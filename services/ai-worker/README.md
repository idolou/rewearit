# ReWearIt AI Worker (`rewearit-ai-worker`)

Asynchronous intelligence worker for ReWearIt second-hand garment platform.

## Responsibilities
- Subscribes to `rewearit.items.events` for `item.created` events.
- Downloads item photos from S3/MinIO, sanitizes and strips EXIF metadata.
- Evaluates Redis SHA-256 cache to prevent duplicate computation.
- Extracts structured garment attributes and condition grades (`ConditionGrade`).
- Encodes a 512-dimensional multimodal visual embedding (L2 normalized).
- Emits `AIAppraisalCompletedEvent` on `rewearit.ai.events`.
- Exposes health probes on port `8002` (`/healthz`, `/ready`).

## Development
```bash
uv sync
uv run pytest tests/
uv run ruff check .
uv run mypy .
```
