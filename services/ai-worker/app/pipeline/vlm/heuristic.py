"""Resilient heuristic VLM client for local/offline appraisal and fallback."""
import io
import re
from PIL import Image

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

COLOR_KEYWORDS = [
    ("Black", [r"\bblack\b", r"\bnoir\b"]),
    ("White", [r"\bwhite\b", r"\bblanc\b"]),
    ("Navy", [r"\bnavy\b", r"\bdark blue\b"]),
    ("Blue", [r"\bblue\b", r"\bdenim\b", r"\bindigo\b"]),
    ("Red", [r"\bred\b", r"\bcrimson\b", r"\bburgundy\b", r"\bmaroon\b"]),
    ("Green", [r"\bgreen\b", r"\bolive\b", r"\bsage\b", r"\bforest\b"]),
    ("Grey", [r"\bgrey\b", r"\bgray\b", r"\bcharcoal\b", r"\bheather\b"]),
    ("Brown", [r"\bbrown\b", r"\bkhaki\b", r"\btan\b", r"\bchocolate\b"]),
    ("Beige", [r"\bbeige\b", r"\bcream\b", r"\bivory\b", r"\boff-white\b"]),
    ("Yellow", [r"\byellow\b", r"\bgold\b", r"\bmustard\b"]),
    ("Pink", [r"\bpink\b", r"\brose\b"]),
    ("Purple", [r"\bpurple\b", r"\bviolet\b", r"\blavender\b"]),
    ("Orange", [r"\borange\b", r"\brust\b"]),
]

MATERIAL_KEYWORDS = [
    ("100% Cotton", [r"\b100% cotton\b", r"\bpure cotton\b"]),
    ("Cotton", [r"\bcotton\b"]),
    ("Denim", [r"\bdenim\b", r"\bjeans\b"]),
    ("Leather", [r"\bleather\b", r"\bcowhide\b"]),
    ("Wool", [r"\bwool\b", r"\bmerino\b", r"\bcashmere\b"]),
    ("Fleece", [r"\bfleece\b", r"\bsherpa\b"]),
    ("Nylon", [r"\bnylon\b", r"\bpolyamide\b"]),
    ("Polyester", [r"\bpolyester\b"]),
    ("Silk", [r"\bsilk\b", r"\bsatin\b"]),
    ("Linen", [r"\blinen\b"]),
    ("Suede", [r"\bsuede\b"]),
]


def _detect_dominant_color_from_image(image_bytes: bytes) -> str:
    """Analyze center region pixels of image to estimate primary color."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            rgb_img = img.convert("RGB")
            width, height = rgb_img.size
            # Sample center 50% of the image
            left = int(width * 0.25)
            top = int(height * 0.25)
            right = int(width * 0.75)
            bottom = int(height * 0.75)
            center_crop = rgb_img.crop((left, top, right, bottom))
            small = center_crop.resize((30, 30))
            pixels = [small.getpixel((x, y)) for x in range(30) for y in range(30)]

            if not pixels:
                return "Black"

            avg_r = sum(p[0] for p in pixels) / len(pixels)
            avg_g = sum(p[1] for p in pixels) / len(pixels)
            avg_b = sum(p[2] for p in pixels) / len(pixels)
            brightness = (avg_r + avg_g + avg_b) / 3.0

            if brightness < 50:
                return "Black"
            if brightness > 220:
                return "White"
            if max(abs(avg_r - avg_g), abs(avg_g - avg_b), abs(avg_r - avg_b)) < 18:
                return "Grey"
            if avg_r > avg_g + 25 and avg_r > avg_b + 25:
                return "Red"
            if avg_b > avg_r + 15 and avg_b > avg_g + 10:
                return "Navy" if brightness < 100 else "Blue"
            if avg_g > avg_r + 15 and avg_g > avg_b + 10:
                return "Green"
            if avg_r > 130 and avg_g > 100 and avg_b < 80:
                return "Brown"
            if avg_r > 180 and avg_g > 160 and avg_b > 130:
                return "Beige"
            return "Blue" if avg_b > avg_r else "Black"
    except Exception:
        return "Black"


class HeuristicVLMClient:
    """Heuristic attribute extraction and appraisal for fast, offline resilience."""

    async def analyze(
        self,
        image_bytes: bytes,
        title: str = "",
        description: str = "",
        declared_condition: str | None = None,
    ) -> VLMAppraisalResult:
        full_text = f"{title} {description}".lower().strip()

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

        # 4. Detect Color
        detected_color = None
        for color_name, patterns in COLOR_KEYWORDS:
            if any(re.search(pat, full_text) for pat in patterns):
                detected_color = color_name
                break
        if not detected_color and image_bytes:
            detected_color = _detect_dominant_color_from_image(image_bytes)
        if not detected_color:
            detected_color = "Black"

        # 5. Detect Size
        explicit_size = re.search(r"\b(?:size|sz)[:\s]*([a-z0-9]+)\b", full_text)
        if explicit_size and explicit_size.group(1).upper() in ("XXS", "XS", "S", "M", "L", "XL", "XXL", "2XL", "3XL"):
            detected_size = explicit_size.group(1).upper()
        else:
            dim_match = re.search(r"\b(\d{2}[xX]\d{2})\b", full_text)
            if dim_match:
                detected_size = dim_match.group(1).upper()
            else:
                shoe_match = re.search(r"\b(us\s*\d+(\.\d+)?|eu\s*\d+|uk\s*\d+)\b", full_text)
                if shoe_match:
                    detected_size = shoe_match.group(1).upper()
                else:
                    size_match = re.search(r"(?<!['’\w])(xxs|xs|s|m|l|xl|xxl|2xl|3xl)(?!['’\w])", full_text)
                    detected_size = size_match.group(1).upper() if size_match else "M"

        # 6. Detect Material
        detected_material = None
        for mat_name, patterns in MATERIAL_KEYWORDS:
            if any(re.search(pat, full_text) for pat in patterns):
                detected_material = mat_name
                break
        if not detected_material:
            if detected_category == "Bottoms":
                detected_material = "Denim"
            elif detected_category == "Outerwear":
                detected_material = "Fleece / Blend"
            else:
                detected_material = "Cotton Blend"

        # 7. Extract Attributes / Tags
        detected_attributes = [
            attr for attr in ATTRIBUTE_KEYWORDS if re.search(r"\b" + attr + r"\b", full_text)
        ]
        if detected_category == "Footwear" and "sneakers" not in detected_attributes:
            detected_attributes.append("sneakers")
        if not detected_attributes:
            detected_attributes = ["casual"]

        # 8. Synthesize Suggested Title
        if title and len(title.strip()) > 3:
            suggested_title = title.strip()
        else:
            brand_part = f"{detected_brand} " if detected_brand != "Unbranded" else ""
            tag_part = f"{detected_attributes[0].capitalize()} " if detected_attributes else ""
            suggested_title = f"{brand_part}{detected_color} {tag_part}{detected_category}".strip()
            suggested_title = re.sub(r"\s+", " ", suggested_title)

        # 9. Calculate Valuation Range
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
            f"color={detected_color}, size={detected_size}, grade={condition_grade} ({confidence:.2f}), "
            f"price=[{min_price}, {target_price}, {max_price}]"
        )

        return VLMAppraisalResult(
            brand=detected_brand,
            category=detected_category,
            condition_grade=condition_grade,
            condition_confidence=confidence,
            detected_attributes=detected_attributes,
            suggested_title=suggested_title,
            detected_color=detected_color,
            detected_size=detected_size,
            detected_material=detected_material,
            suggested_min_price=min_price,
            suggested_target_price=target_price,
            suggested_max_price=max_price,
        )
