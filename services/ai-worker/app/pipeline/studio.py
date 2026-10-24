"""Studio background removal and catalog framing engine for apparel listings."""
import io
import math
from typing import Tuple

from PIL import Image, ImageOps

from app.core.logging import logger

_rembg_available = False
try:
    from rembg import remove as rembg_remove
    _rembg_available = True
except ImportError:
    rembg_remove = None  # type: ignore[assignment]


class StudioEnhancer:
    def __init__(
        self,
        canvas_width: int = 1000,
        canvas_height: int = 1000,
        padding_ratio: float = 0.08,
        background_rgb: Tuple[int, int, int] = (255, 255, 255),
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

        # Fallback: edge-preserving luminosity alpha mask
        return self._fallback_alpha_matting(image_bytes)

    def _fallback_alpha_matting(self, image_bytes: bytes) -> bytes:
        """Fallback background isolation when deep learning model is unavailable."""
        with Image.open(io.BytesIO(image_bytes)) as img:
            rgba = img.convert("RGBA")
            # Analyze corner color to estimate background
            w, h = rgba.size
            corners = [
                rgba.getpixel((0, 0)),
                rgba.getpixel((w - 1, 0)),
                rgba.getpixel((0, h - 1)),
                rgba.getpixel((w - 1, h - 1)),
            ]
            bg_r = sum(c[0] for c in corners) // 4
            bg_g = sum(c[1] for c in corners) // 4
            bg_b = sum(c[2] for c in corners) // 4

            # Create smooth alpha channel based on color distance from estimated background
            r, g, b, _ = rgba.split()
            diff_r = ImageOps.invert(Image.eval(r, lambda x: min(255, abs(x - bg_r) * 2)))
            diff_g = ImageOps.invert(Image.eval(g, lambda x: min(255, abs(x - bg_g) * 2)))
            diff_b = ImageOps.invert(Image.eval(b, lambda x: min(255, abs(x - bg_b) * 2)))

            # Threshold for foreground
            alpha_mask = Image.eval(
                ImageOps.invert(diff_r),
                lambda x: 255 if x > 35 else int((x / 35.0) * 255),
            )
            rgba.putalpha(alpha_mask)

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
