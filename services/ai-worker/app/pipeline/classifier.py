"""Garment classification and studio image enhancement coordinator."""
from typing import Any
from pydantic import BaseModel, Field

from app.pipeline.studio import StudioEnhancer
from app.pipeline.vlm.base import VLMClient
from app.pipeline.vlm.heuristic import HeuristicVLMClient


class AutoFillAttributes(BaseModel):
    title: str = Field(description="Auto-generated suggested listing title")
    category: str = Field(description="Detected garment category (e.g. Outerwear, Tops, Bottoms)")
    brand: str = Field(description="Detected or inferred brand")
    size: str = Field(description="Detected apparel size (e.g. S, M, L, XL, 32x30)")
    color: str = Field(description="Dominant or detected garment color")
    material: str = Field(description="Detected fabric composition")
    condition_grade: str = Field(description="Suggested condition grade")
    confidence: float = Field(ge=0.0, le=1.0, description="Condition classification confidence")
    detected_attributes: list[str] = Field(default_factory=list, description="Style and material tags")


class PriceRangeRecommendation(BaseModel):
    min_price: int = Field(ge=0, description="Lower suggested price bound")
    target_price: int = Field(ge=0, description="Recommended target market price")
    max_price: int = Field(ge=0, description="Upper suggested price bound")


class GarmentClassificationResult(BaseModel):
    clean_image_bytes: bytes = Field(description="Background-removed studio catalog framed image bytes")
    original_image_bytes: bytes = Field(description="Original user-uploaded raw image bytes")
    auto_fill: AutoFillAttributes
    suggested_price_range: PriceRangeRecommendation


class GarmentClassifier:
    """Coordinates studio background removal and multimodal garment attribute classification."""

    def __init__(self, studio: StudioEnhancer | None = None, vlm: VLMClient | None = None) -> None:
        self.studio = studio or StudioEnhancer()
        self.vlm = vlm or HeuristicVLMClient()

    async def classify_and_enhance(
        self,
        image_bytes: bytes,
        hints: dict[str, Any] | None = None,
    ) -> GarmentClassificationResult:
        hints = hints or {}
        title = hints.get("title", "")
        description = hints.get("description", "")
        declared_condition = hints.get("declared_condition")

        # 1. Studio background removal and white catalog canvas framing
        foreground_rgba = self.studio.remove_background(image_bytes)
        clean_catalog_bytes = self.studio.composite_catalog_frame(foreground_rgba)

        # 2. VLM Multimodal analysis
        vlm_res = await self.vlm.analyze(
            image_bytes=image_bytes,
            title=title,
            description=description,
            declared_condition=declared_condition,
        )

        auto_fill = AutoFillAttributes(
            title=vlm_res.suggested_title,
            category=vlm_res.category,
            brand=vlm_res.brand,
            size=vlm_res.detected_size,
            color=vlm_res.detected_color,
            material=vlm_res.detected_material,
            condition_grade=vlm_res.condition_grade,
            confidence=vlm_res.condition_confidence,
            detected_attributes=vlm_res.detected_attributes,
        )

        suggested_price_range = PriceRangeRecommendation(
            min_price=vlm_res.suggested_min_price,
            target_price=vlm_res.suggested_target_price,
            max_price=vlm_res.suggested_max_price,
        )

        return GarmentClassificationResult(
            clean_image_bytes=clean_catalog_bytes,
            original_image_bytes=image_bytes,
            auto_fill=auto_fill,
            suggested_price_range=suggested_price_range,
        )
