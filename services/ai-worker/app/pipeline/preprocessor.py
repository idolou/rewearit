"""Image preprocessor and EXIF metadata stripping."""
import hashlib
import io
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from PIL import Image

from app.core.config import settings
from app.core.logging import logger


def validate_external_image_url(url: str) -> str:
    """Reject non-HTTP(S) schemes and private/loopback/link-local hosts to prevent SSRF."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Image URL must use http or https with a valid hostname")

    # Allow our own configured MinIO/S3 endpoints for internal garment assets
    allowed_s3_bases = {
        settings.S3_ENDPOINT.rstrip("/"),
        settings.S3_PUBLIC_URL.rstrip("/"),
    }
    if any(base and url.startswith(f"{base}/") for base in allowed_s3_bases):
        return url

    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as e:
        raise ValueError(f"Could not resolve hostname '{parsed.hostname}'") from e

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError(f"Access to non-public address ({ip}) is forbidden")

    return url


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

    @staticmethod
    def resolve_internal_url(url: str) -> str:
        """Rewrite s3:// URIs and public S3 URLs to the internal S3 endpoint."""
        if url.startswith("s3://"):
            parts = url.replace("s3://", "", 1).split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""
            return f"{settings.S3_ENDPOINT.rstrip('/')}/{bucket}/{key}"

        public_base = settings.S3_PUBLIC_URL.rstrip("/")
        internal_base = settings.S3_ENDPOINT.rstrip("/")
        if public_base and public_base != internal_base and url.startswith(f"{public_base}/"):
            return f"{internal_base}{url[len(public_base):]}"

        return url

    async def fetch_image(self, url: str) -> bytes:
        """Fetch image bytes from HTTP URL or local MinIO."""
        resolved_url = self.resolve_internal_url(url)
        logger.info(f"Fetching image from url: {resolved_url}")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(resolved_url)
            response.raise_for_status()
            return response.content
