"""Image preprocessor and EXIF metadata stripping."""
import hashlib
import io
from dataclasses import dataclass

import httpx
from PIL import Image

from app.core.config import settings
from app.core.logging import logger


@dataclass
class ProcessedImage:
    sha256: str
    cleaned_bytes: bytes
    width: int
    height: int
    format: str = "JPEG"


class ImagePreprocessor:
    def __init__(self, max_dim: int = 1024) -> None:
        self.max_dim = max_dim

    def process_bytes(self, raw_bytes: bytes) -> ProcessedImage:
        """Strip EXIF metadata, resize within max_dim, and compute sha256."""
        with Image.open(io.BytesIO(raw_bytes)) as img:
            # Convert RGBA / P to RGB
            if img.mode in ("RGBA", "LA", "P"):
                rgb_img = img.convert("RGB")
            elif img.mode != "RGB":
                rgb_img = img.convert("RGB")
            else:
                rgb_img = img.copy()

            # Resize maintaining aspect ratio if larger than max_dim
            orig_w, orig_h = rgb_img.size
            if max(orig_w, orig_h) > self.max_dim:
                scale = self.max_dim / float(max(orig_w, orig_h))
                new_w = int(orig_w * scale)
                new_h = int(orig_h * scale)
                rgb_img = rgb_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            else:
                new_w, new_h = orig_w, orig_h

            # Save clean image without EXIF
            out_buf = io.BytesIO()
            rgb_img.save(out_buf, format="JPEG", quality=90, optimize=True)
            cleaned = out_buf.getvalue()

        # Compute SHA-256 hash
        sha256_hash = hashlib.sha256(cleaned).hexdigest()

        return ProcessedImage(
            sha256=sha256_hash,
            cleaned_bytes=cleaned,
            width=new_w,
            height=new_h,
            format="JPEG",
        )

    async def fetch_image(self, url: str) -> bytes:
        """Fetch image bytes from HTTP URL or local MinIO."""
        logger.info(f"Fetching image from url: {url}")
        if url.startswith("s3://"):
            # MinIO / S3 path: e.g. s3://rewearit-garments/photo.jpg
            # Convert to HTTP endpoint
            parts = url.replace("s3://", "").split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""
            url = f"{settings.S3_ENDPOINT}/{bucket}/{key}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
