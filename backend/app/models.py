from typing import Dict, List, Optional
import math

from pydantic import BaseModel, Field, field_validator, model_validator


class RecommendationFilters(BaseModel):
    min_ram: Optional[float] = Field(default=None, ge=0)
    min_storage: Optional[float] = Field(default=None, ge=0)

    min_price: Optional[float] = Field(default=None, ge=0)
    max_price: Optional[float] = Field(default=None, ge=0)

    min_screen_size: Optional[float] = Field(default=None, ge=0)
    max_screen_size: Optional[float] = Field(default=None, ge=0)

    touch_screen: Optional[bool] = None

    brand: Optional[str] = None
    cpu_brand: Optional[str] = None
    cpu_contains: Optional[str] = None
    gpu_brand: Optional[str] = None
    gpu_contains: Optional[str] = None

    @model_validator(mode="after")
    def validate_price_range(self):
        if (self.min_price is not None and self.max_price is not None
                and self.min_price > self.max_price):
            raise ValueError("Minimum price must not exceed maximum price")
        return self


class RecommendationRequest(BaseModel):
    filters: RecommendationFilters = Field(
        default_factory=RecommendationFilters
    )

    weights: Dict[str, float] = Field(
        ...,
        description=(
            "Canonical aspect IDs mapped to user weights. "
            "Weights do not need to sum to 100."
        ),
    )

    # There are 30 laptops in the thesis dataset, so the API can return all 30.
    top_n: int = Field(default=5, ge=1, le=30)

    @field_validator("weights")
    @classmethod
    def validate_weights(cls, weights):
        if not weights:
            raise ValueError("At least one aspect weight is required.")

        cleaned = {}
        for key, value in weights.items():
            aspect_id = key.strip().upper()

            if value < 0:
                raise ValueError(
                    f"Weight for {aspect_id} cannot be negative."
                )

            cleaned[aspect_id] = float(value)

        if sum(cleaned.values()) <= 0:
            raise ValueError(
                "The sum of aspect weights must be greater than zero."
            )

        return cleaned


class TwoStageRefinementRequest(BaseModel):
    """Verify a Stage-1 shortlist, then rerank only its members.

    The client supplies a frozen Stage-1 snapshot. The server independently
    recomputes it using the original filters and initial preferences.
    """

    filters: RecommendationFilters = Field(default_factory=RecommendationFilters)
    # Original Stage 1 weights are frozen for server-side shortlist verification.
    initial_weights: Dict[str, float]
    # Stage 2 includes ALL Stage 1 aspects (weights may change) AND at least
    # one newly selected aspect. The backend uses these weights for reranking.
    refined_weights: Dict[str, float]
    candidate_laptop_ids: List[str] = Field(..., min_length=1, max_length=10)

    @field_validator("initial_weights", "refined_weights")
    @classmethod
    def validate_stage_weights(cls, weights, info):
        if not weights:
            raise ValueError(f"{info.field_name} must contain at least one aspect")
        clean = {}
        for raw_id, value in weights.items():
            aspect_id = raw_id.strip().upper()
            if not aspect_id or aspect_id in clean:
                raise ValueError("Preference aspect IDs must be distinct and non-empty")
            if not math.isfinite(value) or value <= 0:
                raise ValueError("All guided preference weights must be positive and finite")
            clean[aspect_id] = float(value)
        return clean

    @field_validator("candidate_laptop_ids")
    @classmethod
    def validate_candidates(cls, ids):
        if any(not name or not name.strip() for name in ids):
            raise ValueError("Candidate laptop IDs cannot be blank")
        if len(ids) != len(set(ids)):
            raise ValueError("Candidate laptop IDs cannot be duplicated")
        return ids

    @model_validator(mode="after")
    def ensure_refinement_extends_initial_preferences(self):
        initial = set(self.initial_weights)
        refined = set(self.refined_weights)
        missing = initial - refined
        if missing:
            raise ValueError(f"Stage 2 must retain every Stage 1 aspect: {sorted(missing)}")
        if not refined - initial:
            raise ValueError("Stage 2 must add at least one new aspect")
        return self


class AspectBreakdown(BaseModel):
    aspect_id: str
    aspect_name: str
    normalized_weight: float

    positive_reviews: int
    negative_reviews: int
    neutral_reviews: int
    mixed_reviews: int
    mention_count: int

    positive_ratio: Optional[float]
    raw_sentiment_score: Optional[float]
    prior_score: float
    adjusted_score: float

    evidence_confidence: float
    evidence_level: str
    has_direct_evidence: bool

    weighted_score_contribution: float
    weighted_confidence_contribution: float


class RecommendationItem(BaseModel):
    rank: int

    laptop_id: str
    laptop: str
    brand: Optional[str]
    processor: Optional[str]
    gpu: Optional[str]
    operating_system: Optional[str]

    price_usd: Optional[float]
    ram_gb: Optional[float]
    storage_gb: Optional[float]
    storage_type: Optional[str]

    screen_size_in: Optional[float]
    screen_resolution: Optional[str]
    refresh_rate_hz: Optional[float]
    touch_screen: Optional[bool]
    weight_lb: Optional[float]

    image_url: Optional[str]
    product_url: Optional[str]

    recommendation_score: float
    recommendation_score_0_100: float

    evidence_confidence: float
    evidence_confidence_0_100: float

    selected_aspects: int
    selected_aspects_with_evidence: int
    selected_aspects_without_evidence: int

    aspect_breakdown: List[AspectBreakdown]


class RecommendationResponse(BaseModel):
    normalized_weights: Dict[str, float]
    filters: RecommendationFilters
    result_count: int
    recommendations: List[RecommendationItem]


class AspectInfo(BaseModel):
    aspect_id: str
    aspect_name: str
    prior_score: Optional[float]
    prior_positive_ratio: Optional[float]
    laptops_with_evidence: Optional[int]
    total_reviews_mentioning_aspect: Optional[int]


class FilterOptionsResponse(BaseModel):
    brands: List[str]
    cpu_brands: List[str]
    gpu_brands: List[str]

    ram_options_gb: List[float]
    storage_options_gb: List[float]
    screen_size_options_in: List[float]

    min_price_usd: Optional[float]
    max_price_usd: Optional[float]


class LaptopDetail(BaseModel):
    laptop_id: str
    product_name: str
    brand: Optional[str]
    model: Optional[str]

    processor: Optional[str]
    gpu: Optional[str]
    operating_system: Optional[str]

    price_usd: Optional[float]
    ram_gb: Optional[float]
    ram_type: Optional[str]
    ram_speed_mhz: Optional[float]

    storage_gb: Optional[float]
    storage_type: Optional[str]

    screen_size_in: Optional[float]
    screen_resolution: Optional[str]
    display_type: Optional[str]
    screen_type: Optional[str]
    refresh_rate_hz: Optional[float]
    brightness_nits: Optional[float]
    touch_screen: Optional[bool]

    weight_lb: Optional[float]
    battery_life_hours: Optional[float]

    image_url: Optional[str]
    product_url: Optional[str]

    aspects: List[dict]

    # Approved, offline-generated summaries stored on Laptop nodes.
    overall_summary: Optional[str] = None
    strengths_summary: Optional[str] = None
    weaknesses_summary: Optional[str] = None
    summary_evidence_note: Optional[str] = None
    summary_model: Optional[str] = None
    summary_prompt_version: Optional[str] = None
    summary_source_hash: Optional[str] = None


class EvidenceSummary(BaseModel):
    positive_reviews: int
    negative_reviews: int
    neutral_reviews: int
    mixed_reviews: int
    mention_count: int


class ReviewEvidenceItem(BaseModel):
    review_key: str
    source_review_id: Optional[int]
    review_date: Optional[str]
    sentiment: str
    snippet: str
    raw_aspects: Optional[str]


class AspectEvidenceResponse(BaseModel):
    laptop_id: str
    laptop: str

    aspect_id: str
    aspect_name: str

    adjusted_score: float
    adjusted_score_0_100: float
    evidence_confidence: float
    evidence_confidence_0_100: float
    evidence_level: str
    has_direct_evidence: bool

    summary: EvidenceSummary

    total_available_reviews: int
    returned_reviews: int
    reviews: List[ReviewEvidenceItem]
