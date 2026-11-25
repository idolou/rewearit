"""Unit tests for ImagePreprocessor."""
import io

from PIL import Image

from app.pipeline.preprocessor import ImagePreprocessor, ProcessedImage


def create_sample_image(width: int = 1200, height: int = 800, color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_process_image_bytes() -> None:
    raw_bytes = create_sample_image(width=1600, height=1200)
    preprocessor = ImagePreprocessor(max_dim=1024)

    result: ProcessedImage = preprocessor.process_bytes(raw_bytes)

    assert isinstance(result.sha256, str)
    assert len(result.sha256) == 64
    assert result.width <= 1024
    assert result.height <= 1024
    assert len(result.cleaned_bytes) > 0

    # Ensure processed image is readable and stripped
    processed_img = Image.open(io.BytesIO(result.cleaned_bytes))
    assert processed_img.size == (1024, 768)
    assert processed_img.getexif() == {}


def test_resolve_internal_url(monkeypatch: object) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "S3_PUBLIC_URL", "http://localhost:9000")  # type: ignore[attr-defined]
    monkeypatch.setattr(settings, "S3_ENDPOINT", "http://minio:9000")  # type: ignore[attr-defined]

    assert (
        ImagePreprocessor.resolve_internal_url("http://localhost:9000/rewearit-garments/clean/a.jpg")
        == "http://minio:9000/rewearit-garments/clean/a.jpg"
    )
    assert (
        ImagePreprocessor.resolve_internal_url("s3://rewearit-garments/clean/a.jpg")
        == "http://minio:9000/rewearit-garments/clean/a.jpg"
    )
    assert (
        ImagePreprocessor.resolve_internal_url("https://cdn.example.com/photo.jpg")
        == "https://cdn.example.com/photo.jpg"
    )
