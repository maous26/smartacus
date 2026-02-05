"""
Smartacus Events Module
=======================

Event detection and processing for opportunity identification.

Components:
    - Event Models: Data structures for different event types
    - Event Processor: Detection and persistence logic
    - Event Aggregator: Metrics aggregation for scoring

Event Types:
    - PriceEvent: Significant price changes (>5%)
    - BSREvent: BSR movements (>20% or >10K positions)
    - StockEvent: Stock status transitions (stockouts, restocks)

Usage:
    from src.events import PriceEvent, BSREvent, StockEvent

    # Events are created by EventProcessor from snapshot comparisons
"""

from .event_models import (
    # Enums
    EventSeverity,
    MovementDirection,
    StockTransitionType,
    # Core Events
    PriceEvent,
    BSREvent,
    StockEvent,
    # Metrics
    SellerChurnMetrics,
    BuyboxMetrics,
    AggregatedEventMetrics,
    MarketSignals,
)

from .economic_events import (
    # Types d'événements économiques
    EconomicEventType,
    EventConfidence,
    EventUrgency,
    # Événements économiques (thèses)
    EconomicEvent,
    SupplyShockEvent,
    CompetitorCollapseEvent,
    QualityDecayEvent,
    PriceElasticityEvent,
    DemandSurgeEvent,
    # Détecteur
    EconomicEventDetector,
)

__all__ = [
    # Enums (symptômes)
    "EventSeverity",
    "MovementDirection",
    "StockTransitionType",
    # Events symptômes
    "PriceEvent",
    "BSREvent",
    "StockEvent",
    # Metrics
    "SellerChurnMetrics",
    "BuyboxMetrics",
    "AggregatedEventMetrics",
    "MarketSignals",
    # === ÉCONOMIQUES (thèses) ===
    "EconomicEventType",
    "EventConfidence",
    "EventUrgency",
    "EconomicEvent",
    "SupplyShockEvent",
    "CompetitorCollapseEvent",
    "QualityDecayEvent",
    "PriceElasticityEvent",
    "DemandSurgeEvent",
    "EconomicEventDetector",
]
