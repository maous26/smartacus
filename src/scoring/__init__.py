"""
Smartacus Scoring Module
========================

Deterministic opportunity scoring for Amazon products.

Components:
    - OpportunityScorer: Base scoring engine (100% deterministic)
    - EconomicScorer: Scoring avec coût du temps intégré

PHILOSOPHIE:
    - OpportunityScorer: score = composantes additives
    - EconomicScorer: score = base × time_multiplier × value

Le temps n'est pas une composante. Le temps est un MULTIPLICATEUR.

Usage:
    from src.scoring import EconomicScorer

    scorer = EconomicScorer()
    result = scorer.score_economic(product_data, time_data)

    print(result.final_score)
    print(result.rank_score)  # valeur × urgence
"""

from .opportunity_scorer import (
    OpportunityScorer,
    ScoringResult,
    ComponentScore,
    OpportunityStatus,
)
from .scoring_config import (
    ScoringConfig,
    DEFAULT_CONFIG,
)
from .economic_scorer import (
    EconomicScorer,
    EconomicOpportunity,
    TimeWindow,
    TimeMultiplierResult,
)

__all__ = [
    # Base scorer
    "OpportunityScorer",
    "ScoringResult",
    "ComponentScore",
    "OpportunityStatus",
    "ScoringConfig",
    "DEFAULT_CONFIG",
    # Economic scorer (avec coût du temps)
    "EconomicScorer",
    "EconomicOpportunity",
    "TimeWindow",
    "TimeMultiplierResult",
]
