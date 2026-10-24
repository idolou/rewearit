"""Unit tests for StudioEnhancer background removal and catalog framing."""
import io

from PIL import Image, ImageDraw

from app.pipeline.studio import StudioEnhancer


def _generate_test_garment_image() -> bytes:
    """Generate a synthetic garment image (blue jacket on noisy background)."""
    img = Image.new("RGB", (600, 800), color=(180, 160, 140))  # Beige noisy background
    draw = ImageDraw.Draw(img)
    # Draw simple garment body & sleeves
    draw.polygon([(200, 200), (400, 200), (450, 700), (150, 700)], fill=(30, 80, 160))  # Denim blue
    draw.polygon([(200, 200), (100, 450), (140, 500), (230, 260)], fill=(25, 70, 140))  # Left sleeve
    draw.polygon([(400, 200), (500, 450), (460, 500), (370, 260)], fill=(25, 70, 140))  # Right sleeve

    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_studio_enhancer_remove_background() -> None:
    enhancer = StudioEnhancer()
    raw = _generate_test_garment_image()
    foreground = enhancer.remove_background(raw)

    assert foreground is not None
    assert len(foreground) > 0

    with Image.open(io.BytesIO(foreground)) as img:
        assert img.mode == "RGBA"


def test_studio_enhancer_composite_catalog_frame() -> None:
    enhancer = StudioEnhancer(canvas_width=800, canvas_height=800, padding_ratio=0.1)
    raw = _generate_test_garment_image()
    foreground = enhancer.remove_background(raw)
    catalog_frame = enhancer.composite_catalog_frame(foreground, output_format="JPEG")

    assert catalog_frame is not None
    assert len(catalog_frame) > 0

    with Image.open(io.BytesIO(catalog_frame)) as img:
        assert img.size == (800, 800)
        assert img.mode == "RGB"


def test_studio_enhancer_create_catalog_ready_image() -> None:
    enhancer = StudioEnhancer(canvas_width=500, canvas_height=500)
    raw = _generate_test_garment_image()
    output = enhancer.create_catalog_ready_image(raw)

    with Image.open(io.BytesIO(output)) as img:
        assert img.size == (500, 500)
        assert img.mode == "RGB"


def test_studio_enhancer_yellow_garment_on_white_background() -> None:
    """Ensure yellow garment on white background is not erased by alpha matting."""
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 150, 150], fill=(255, 220, 0))  # Yellow garment (red channel identical to white)
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    enhancer = StudioEnhancer()
    foreground = enhancer.remove_background(buf.getvalue())
    with Image.open(io.BytesIO(foreground)) as res:
        center_alpha = res.getpixel((100, 100))[3]
        assert center_alpha > 150

