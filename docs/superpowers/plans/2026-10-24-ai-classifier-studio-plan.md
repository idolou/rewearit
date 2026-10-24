# AI Garment Classifier & Studio Background Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
Build an automated AI classifier and studio image enhancement pipeline for seller uploads:
1. **Studio Background Removal:** Strips messy backgrounds (bedroom, hangers, floor) and composites the garment onto a clean studio catalog canvas (`#FFFFFF` with centered padding).
2. **Attribute Classification & Auto-Fill:** Multimodal analysis extracting `title`, `category`, `brand`, `size`, `color`, `material`, and `condition_grade`.
3. **Seller Price Guidance:** Calculates a fair-market valuation range (`suggested_min_price`, `suggested_target_price`, `suggested_max_price`), while allowing the seller to adjust any auto-populated field and pick their final price before publishing.

**Tech Stack:** Python 3.12, FastAPI, PIL / Pillow, rembg (with graceful fallback), MinIO S3, Pytest.

---

## Tasks

### Task 1: Studio Background Removal & Framing Engine
**Files:**
- Modify: `services/ai-worker/pyproject.toml` (add `rembg>=2.0.50`, `numpy`, `scipy`)
- Create: `services/ai-worker/app/pipeline/studio.py`
- Test: `services/ai-worker/tests/unit/test_studio.py`

- [ ] Add `rembg` and image processing libraries to `services/ai-worker/pyproject.toml`.
- [ ] Implement `StudioEnhancer` in `app/pipeline/studio.py`:
  - `remove_background(image_bytes: bytes) -> bytes`: Extracts foreground garment with alpha channel.
  - `composite_catalog_frame(foreground_rgba: bytes, bg_color: tuple[int, int, int] = (255, 255, 255), padding_ratio: float = 0.08) -> bytes`: Centers garment on white studio background with balanced margin.
  - Graceful fallback: If ONNX model fails to load, performs smart edge-feathered canvas framing so the pipeline never crashes.
- [ ] Write unit tests verifying transparent PNG handling, canvas padding, and fallback execution.
- [ ] Commit: `feat(ai-worker): implement studio background removal and catalog framing`.

---

### Task 2: Multimodal Attribute Auto-Fill & Price Estimation
**Files:**
- Modify: `services/ai-worker/app/pipeline/vlm/base.py` (expand attributes: `title`, `color`, `material`)
- Modify: `services/ai-worker/app/pipeline/vlm/heuristic.py` (extract color, size, and title heuristics)
- Create: `services/ai-worker/app/pipeline/classifier.py`
- Test: `services/ai-worker/tests/unit/test_classifier.py`

- [ ] Expand `VLMAppraisalResult` schema to include:
  - `suggested_title: str`
  - `detected_color: str`
  - `detected_size: str`
  - `detected_material: str`
  - `suggested_target_price: int`
- [ ] Implement `GarmentClassifier` in `app/pipeline/classifier.py` coordinating `StudioEnhancer` and `VLMClient`.
- [ ] Write unit tests verifying comprehensive attribute extraction and price range calculation.
- [ ] Commit: `feat(ai-worker): implement garment attribute auto-fill and price range estimation`.

---

### Task 3: MinIO S3 Image Storage & AI Worker Classification API
**Files:**
- Modify: `services/ai-worker/app/server.py`
- Modify: `services/ai-worker/app/core/config.py` (ensure S3 bucket configuration)
- Test: `services/ai-worker/tests/integration/test_classify_api.py`

- [ ] Add S3 upload helper in `ai-worker` to store raw and studio-enhanced images in `rewearit-garments` bucket.
- [ ] Add `POST /api/v1/classify` endpoint to `services/ai-worker/app/server.py`:
  - Accepts `UploadFile` (multipart) or JSON `{ "image_url": "..." }`.
  - Runs studio enhancement -> stores clean catalog image.
  - Runs attribute classifier -> extracts auto-fill fields & price range.
  - Returns `{ clean_image_url, original_image_url, auto_fill, suggested_price_range }`.
- [ ] Write integration test verifying the `/api/v1/classify` response contract.
- [ ] Commit: `feat(ai-worker): expose interactive classification and studio enhancement API`.

---

### Task 4: Catalog Service Integration & Interactive Seller Form
**Files:**
- Modify: `services/catalog-service/app/models/item.py` (add `color`, `material` fields to `ItemBase`)
- Modify: `services/catalog-service/app/api/v1/items.py` (add `POST /api/v1/items/classify` proxy endpoint)
- Create: `services/catalog-service/app/static/upload_preview.html` (interactive seller upload demo)
- Test: `services/catalog-service/tests/unit/test_items_api.py`

- [ ] Add optional `color` and `material` columns to `ItemBase` in `services/catalog-service/app/models/item.py`.
- [ ] Add `POST /api/v1/items/classify` endpoint in `catalog-service` delegating to `ai-worker:8002/api/v1/classify`.
- [ ] Add a clean interactive upload preview page (`/upload`) demonstrating:
  1. Drag-and-drop garment photo.
  2. Side-by-side display of original vs studio-cleaned photo.
  3. Form auto-populated with AI values.
  4. Editable price input with suggested price range chips (`Min`, `Target`, `Max`).
  5. One-click publish to `POST /api/v1/items`.
- [ ] Write unit and integration tests for `items.py` classification routing.
- [ ] Commit: `feat(catalog): integrate classification endpoint and seller preview form`.

---

### Task 5: End-to-End Verification & Docker Compose Integration
**Files:**
- Modify: `deploy/docker-compose/docker-compose.yml`
- Test: End-to-end curl verification of upload -> classify -> edit -> publish.

- [ ] Rebuild `ai-worker:local` and `catalog-service:local` images.
- [ ] Execute live verification test:
  1. Upload image to `POST /api/v1/items/classify`.
  2. Verify clean background-removed image is created.
  3. Verify auto-fill fields and suggested price range.
  4. Publish item with user-customized price and clean image URL.
  5. Verify item is in catalog with user's chosen price!
- [ ] Commit & push to GitHub `idolou/rewearit`.
