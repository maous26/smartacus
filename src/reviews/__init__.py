"""
Smartacus Review Intelligence Engine
=====================================

Deterministic extraction of product defects and improvement signals
from Amazon reviews. No ML required for V1.

Modules:
    review_models   — Data models (DefectSignal, FeatureRequest, ImprovementProfile)
    review_signals  — Deterministic defect extraction via niche-specific lexicon
    review_insights — Aggregation into per-ASIN improvement profiles
"""

from .review_models import DefectSignal, FeatureRequest, ProductImprovementProfile
from .review_signals import ReviewSignalExtractor, DEFECT_LEXICON
from .review_insights import ReviewInsightAggregator
