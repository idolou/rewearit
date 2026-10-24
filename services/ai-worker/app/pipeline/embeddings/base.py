"""Base interface for multimodal visual embedding generators."""
from typing import Protocol


class EmbeddingGenerator(Protocol):
    def encode_image(self, image_bytes: bytes, context_text: str = "") -> list[float]:
        """Produce a normalized 512-dimensional float vector."""
        ...
