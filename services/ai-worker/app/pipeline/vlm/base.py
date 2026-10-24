"""Base definitions and protocols for Vision-Language Model (VLM) clients."""
from typing import Protocol

from pydantic import BaseModel, Field


class VLMAppraisalResult(BaseModel):
    brand: str = Field(description="Detected or inferred garment brand (e.g., Levi's, Nike, Zara)")
    category: str = Field(description="Garment category (e.g., Outerwear, Footwear, Tops, Bottoms)")
    condition_grade: str = Field(
        description="Canonical condition grade (NEW_WITH_TAGS, EXCELLENT, VERY_GOOD, GOOD, FAIR)"
    )
    condition_confidence: float = Field(ge=0.0, le=1.0, description="Confidence score for the condition grade")
    detected_attributes: list[str] = Field(default_factory=list, description="Descriptive style and material tags")
    suggested_min_price: int = Field(ge=0, description="Suggested fair market lower price bound in whole units")
    suggested_max_price: int = Field(ge=0, description="Suggested fair market upper price bound in whole units")


class VLMClient(Protocol):
    async def analyze(
        self,
        image_bytes: bytes,
        title: str,
        description: str,
        declared_condition: str | None = None,
    ) -> VLMAppraisalResult:
        """Analyze garment photos and listing text to extract structured appraisal metadata."""
        ...
