"""Unit tests for 512-dimensional multimodal visual embedding encoder."""
import math

from app.pipeline.embeddings.encoder import VisualEmbeddingEncoder


def test_embedding_dimensions_and_normalization() -> None:
    encoder = VisualEmbeddingEncoder(dimension=512)
    sample_bytes = b"image_data_for_embedding_verification"

    embedding = encoder.encode_image(sample_bytes, context_text="Vintage Denim Jacket")

    assert len(embedding) == 512
    # Verify L2-norm == 1.0 (unit vector for cosine distance)
    norm = math.sqrt(sum(x * x for x in embedding))
    assert abs(norm - 1.0) < 1e-4


def test_embedding_deterministic_consistency() -> None:
    encoder = VisualEmbeddingEncoder(dimension=512)
    sample_bytes = b"same_image_bytes"

    emb1 = encoder.encode_image(sample_bytes, context_text="Black hoodie")
    emb2 = encoder.encode_image(sample_bytes, context_text="Black hoodie")

    assert emb1 == emb2


def test_cosine_similarity() -> None:
    encoder = VisualEmbeddingEncoder(dimension=512)

    emb_denim1 = encoder.encode_image(b"denim1", context_text="Blue denim jacket")
    emb_denim2 = encoder.encode_image(b"denim2", context_text="Blue denim trucker jacket")
    emb_dress = encoder.encode_image(b"dress1", context_text="Silk evening gown dress")

    sim_denim = sum(a * b for a, b in zip(emb_denim1, emb_denim2, strict=True))
    sim_diff = sum(a * b for a, b in zip(emb_denim1, emb_dress, strict=True))

    assert sim_denim > sim_diff
