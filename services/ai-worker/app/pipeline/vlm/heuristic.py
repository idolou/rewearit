"""Resilient heuristic VLM client for local/offline appraisal and fallback."""
import re

from app.core.logging import logger
from app.pipeline.vlm.base import VLMAppraisalResult

KNOWN_BRANDS = [
    "Levi's", "Levis", "Nike", "Adidas", "Jordan", "Patagonia", "Arc'teryx",
    "Carhartt", "Ralph Lauren", "Polo", "Zara", "H&M", "Uniqlo", "Stussy",
    "Supreme", "Gucci", "Prada", "Balenciaga", "The North Face", "Champion",
]

CATEGORY_PATTERNS = [
    ("Outerwear", [r"\bjacket\b", r"\bcoat\b", r"\bbomber\b", r"\bwindbreaker\b", r"\bparker\b", r"\bparka\b", r"\bfleece\b", r"\bblazer\b"]),
    ("Footwear", [r"\bsneaker", r"\bshoe", r"\bboot", r"\bloafer", r"\bsandal", r"\bjordan\b", r"\bdunk\b"]),
    ("Bottoms", [r"\bjean", r"\bpant", r"\btrouser", r"\bshort", r"\bdenim\b", r"\bcargo\b"]),
    ("Tops", [r"\bshirt\b", r"\btee\b", r"\bt-shirt\b", r"\bhoodie\b", r"\bsweater\b", r"\bcardigan\b", r"\btop\b"]),
    ("Dresses", [r"\bdress\b", r"\bgown\b", r"\bskirt\b"]),
]

ATTRIBUTE_KEYWORDS = [
    "vintage", "denim", "distressed", "cotton", "leather", "wool", "silk",
    "streetwear", "90s", "y2k", "oversized", "retro", "casual", "embroidered",
    "striped", "graphic", "monogram", "fleece", "nylon", "sneakers", "sneaker",
]


class HeuristicVLMClient:
    """Heuristic attribute extraction and appraisal for fast, offline resilience."""

    async def analyze(
        self,
        image_bytes: bytes,
        title: str,
        description: str,
        declared_condition: str | None = None,
    ) -> VLMAppraisalResult:
        full_text = f"{title} {description}".lower()

        # 1. Detect Brand
        detected_brand = "Unbranded"
        for brand in KNOWN_BRANDS:
            if re.search(r"\b" + re.escape(brand.lower()) + r"\b", full_text):
                detected_brand = brand
                break

        # 2. Detect Category
        detected_category = "Tops"
        for category, patterns in CATEGORY_PATTERNS:
            if any(re.search(pat, full_text) for pat in patterns):
                detected_category = category
                break

        # 3. Detect Condition Grade
        condition_grade = "GOOD"
        confidence = 0.82

        if re.search(r"\b(new with tags|nwt|never worn|brand new|deadstock)\b", full_text):
            condition_grade = "NEW_WITH_TAGS"
            confidence = 0.94
        elif re.search(r"\b(flawless|mint condition|like new|pristine|excellent condition|excellent)\b", full_text):
            condition_grade = "EXCELLENT"
            confidence = 0.90
        elif re.search(r"\b(very good|gentle wear|lightly used|minor wear|slight fraying)\b", full_text):
            condition_grade = "VERY_GOOD"
            confidence = 0.88
        elif re.search(r"\b(flaw|stain|rip|tear|hole|fair condition|heavy wear)\b", full_text):
            condition_grade = "FAIR"
            confidence = 0.85
        elif declared_condition and declared_condition.upper() in (
            "NEW_WITH_TAGS", "EXCELLENT", "VERY_GOOD", "GOOD", "FAIR"
        ):
            condition_grade = declared_condition.upper()
            confidence = 0.85

        # 4. Extract Attributes / Tags
        detected_attributes = [
            attr for attr in ATTRIBUTE_KEYWORDS if re.search(r"\b" + attr + r"\b", full_text)
        ]
        if detected_category == "Footwear" and "sneakers" not in detected_attributes:
            detected_attributes.append("sneakers")
        if not detected_attributes:
            detected_attributes = ["casual"]

        # 5. Calculate Valuation Range
        base_price = 30
        if detected_brand in ("Gucci", "Prada", "Balenciaga", "Arc'teryx"):
            base_price = 220
        elif detected_brand in ("Nike", "Jordan", "Supreme", "Levi's", "Carhartt", "Patagonia"):
            base_price = 65

        if detected_category in ("Outerwear", "Footwear"):
            base_price = int(base_price * 1.4)
        elif detected_category == "Dresses":
            base_price = int(base_price * 1.2)

        condition_multiplier = {
            "NEW_WITH_TAGS": 1.3,
            "EXCELLENT": 1.15,
            "VERY_GOOD": 1.0,
            "GOOD": 0.85,
            "FAIR": 0.65,
        }.get(condition_grade, 0.85)

        target_price = int(base_price * condition_multiplier)
        min_price = max(10, int(target_price * 0.8))
        max_price = int(target_price * 1.25)

        logger.info(
            f"Heuristic appraisal completed: brand={detected_brand}, category={detected_category}, "
            f"grade={condition_grade} ({confidence:.2f}), fmv=[{min_price}, {max_price}]"
        )

        return VLMAppraisalResult(
            brand=detected_brand,
            category=detected_category,
            condition_grade=condition_grade,
            condition_confidence=confidence,
            detected_attributes=detected_attributes,
            suggested_min_price=min_price,
            suggested_max_price=max_price,
        )
