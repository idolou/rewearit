"""Studio background removal and catalog framing engine for apparel listings."""
import io

import numpy as np
from PIL import Image

from app.core.logging import logger

_rembg_available = False
try:
    from rembg import remove as rembg_remove
    _rembg_available = True
except ImportError:
    rembg_remove = None


class StudioEnhancer:
    def __init__(
        self,
        canvas_width: int = 1000,
        canvas_height: int = 1000,
        padding_ratio: float = 0.08,
        background_rgb: tuple[int, int, int] = (255, 255, 255),
    ) -> None:
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.padding_ratio = padding_ratio
        self.background_rgb = background_rgb

    def remove_background(self, image_bytes: bytes) -> bytes:
        """Remove image background returning an RGBA image with transparent alpha channel."""
        if _rembg_available and rembg_remove is not None:
            try:
                logger.info("Extracting garment foreground using rembg deep learning model...")
                output_bytes = rembg_remove(image_bytes)
                if output_bytes:
                    return output_bytes
            except Exception as e:
                logger.warning(f"rembg background removal encountered an issue ({e}), using fallback matting")

        # Fallback: multi-channel Euclidean color distance alpha mask
        return self._fallback_alpha_matting(image_bytes)

    def _fallback_alpha_matting(self, image_bytes: bytes) -> bytes:
        """Fallback background isolation using multi-channel Euclidean color distance."""
        with Image.open(io.BytesIO(image_bytes)) as img:
            rgba = img.convert("RGBA")
            arr = np.array(rgba, dtype=np.float32)
            rgb = arr[:, :, :3]

            # Average 4 corner pixel colors to estimate background
            bg_vec = (arr[0, 0, :3] + arr[0, -1, :3] + arr[-1, 0, :3] + arr[-1, -1, :3]) / 4.0

            # Euclidean color distance across all 3 color channels
            dist = np.linalg.norm(rgb - bg_vec, axis=2)

            # Smoothstep alpha thresholding (dist < 15 -> 0, dist > 40 -> 255)
            alpha = np.clip((dist - 15.0) / 25.0 * 255.0, 0, 255).astype(np.uint8)
            alpha_img = Image.fromarray(alpha, mode="L")
            rgba.putalpha(alpha_img)

            out = io.BytesIO()
            rgba.save(out, format="PNG")
            return out.getvalue()

    def composite_catalog_frame(
        self,
        foreground_rgba_bytes: bytes,
        output_format: str = "JPEG",
        quality: int = 95,
    ) -> bytes:
        """Center and scale garment on clean studio background with balanced catalog margins."""
        with Image.open(io.BytesIO(foreground_rgba_bytes)) as img:
            rgba = img.convert("RGBA")

            # Crop tight bounding box around the garment based on alpha channel
            bbox = rgba.getbbox()
            if bbox:
                cropped = rgba.crop(bbox)
            else:
                cropped = rgba

            # Compute maximum allowed dimensions within canvas padding
            max_w = int(self.canvas_width * (1.0 - 2 * self.padding_ratio))
            max_h = int(self.canvas_height * (1.0 - 2 * self.padding_ratio))

            crop_w, crop_h = cropped.size
            if crop_w > 0 and crop_h > 0:
                scale = min(max_w / crop_w, max_h / crop_h)
                new_w = max(1, int(crop_w * scale))
                new_h = max(1, int(crop_h * scale))
                resized = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)
            else:
                resized = cropped
                new_w, new_h = crop_w, crop_h

            # Create clean studio canvas
            canvas = Image.new("RGBA", (self.canvas_width, self.canvas_height), (*self.background_rgb, 255))

            # Center position
            offset_x = (self.canvas_width - new_w) // 2
            offset_y = (self.canvas_height - new_h) // 2

            canvas.paste(resized, (offset_x, offset_y), mask=resized)

            out = io.BytesIO()
            if output_format.upper() in ("JPEG", "JPG"):
                rgb_canvas = canvas.convert("RGB")
                rgb_canvas.save(out, format="JPEG", quality=quality, optimize=True)
            else:
                canvas.save(out, format="PNG", optimize=True)

            return out.getvalue()

    def create_catalog_ready_image(self, raw_image_bytes: bytes) -> bytes:
        """End-to-end studio pipeline: background removal + studio catalog framing."""
        foreground = self.remove_background(raw_image_bytes)
        return self.composite_catalog_frame(foreground)
