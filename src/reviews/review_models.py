"""
Review Intelligence Data Models
================================

Structured outputs from the review analysis pipeline.
These map directly to the DB tables in migration 005.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class DefectType(str, Enum):
    """Defect categories for Car Phone Mounts niche."""
    MECHANICAL_FAILURE = "mechanical_failure"
    POOR_GRIP = "poor_grip"
    INSTALLATION_ISSUE = "installation_issue"
    COMPATIBILITY_ISSUE = "compatibility_issue"
    MATERIAL_QUALITY = "material_quality"
    VIBRATION_NOISE = "vibration_noise"
    HEAT_ISSUE = "heat_issue"
    SIZE_FIT = "size_fit"
    DURABILITY = "durability"
    OTHER = "other"


@dataclass
class DefectSignal:
    """A single defect signal extracted from reviews (deterministic)."""
    defect_type: str
    frequency: int              # number of reviews mentioning this defect
    severity_score: float       # 0.0 to 1.0 (computed from frequency + keyword weight)
    example_quotes: List[str]   # max 3 verbatim quotes
    total_reviews_scanned: int
    negative_reviews_scanned: int

    @property
    def frequency_rate(self) -> float:
        """Defect frequency as % of negative reviews."""
        if self.negative_reviews_scanned == 0:
            return 0.0
        return self.frequency / self.negative_reviews_scanned


@dataclass
class FeatureRequest:
    """A missing feature detected from 'I wish' patterns (LLM or regex)."""
    feature: str
    mentions: int
    confidence: float           # 0.0 to 1.0
    source_quotes: List[str] = field(default_factory=list)
    helpful_votes: int = 0      # cumulative helpful votes across matching reviews
    wish_strength: float = 0.0  # mentions + log1p(helpful_votes) — business priority


@dataclass
class ProductImprovementProfile:
    """Aggregated improvement profile for one ASIN."""
    asin: str
    top_defects: List[DefectSignal]
    missing_features: List[FeatureRequest]
    dominant_pain: Optional[str]        # the #1 most impactful defect type
    improvement_score: float            # 0.0 to 1.0
    reviews_analyzed: int
    negative_reviews_analyzed: int
    reviews_ready: bool                 # True if reviews were available

    @property
    def has_actionable_insights(self) -> bool:
        """True if there are defects with severity > 0.3."""
        return any(d.severity_score > 0.3 for d in self.top_defects)

    def to_thesis_fragment(self) -> str:
        """Generate a thesis fragment for the economic thesis."""
        if not self.top_defects:
            return ""

        parts = []
        if self.dominant_pain:
            top = self.top_defects[0]
            parts.append(
                f"{top.frequency_rate:.0%} des avis negatifs mentionnent '{top.defect_type}'"
            )

        if self.missing_features:
            best = self.missing_features[0]
            parts.append(f"Feature demandee: '{best.feature}' ({best.mentions} mentions)")

        if self.improvement_score > 0.6:
            parts.append("Defaut facilement corrigeable OEM")
        elif self.improvement_score > 0.3:
            parts.append("Amelioration produit possible")

        return " | ".join(parts)
