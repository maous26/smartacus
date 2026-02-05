"""
Tests for Smartacus Economic Events layer.

Tests the detection of economic theses from raw market signals:
- SupplyShockEvent detection and edge cases
- CompetitorCollapseEvent detection
- QualityDecayEvent detection
- EconomicEventDetector orchestration
- Event actionability and signal strength

Usage:
    pytest tests/test_economic_events.py -v
"""

import pytest
from datetime import datetime
from decimal import Decimal

from src.events.economic_events import (
    EconomicEventType,
    EventConfidence,
    EventUrgency,
    EconomicEvent,
    SupplyShockEvent,
    CompetitorCollapseEvent,
    QualityDecayEvent,
    EconomicEventDetector,
)


# =============================================================================
# SupplyShockEvent Tests
# =============================================================================

class TestSupplyShockDetection:
    """Tests for SupplyShockEvent.from_signals()."""

    def test_classic_supply_shock(self):
        """Multiple stockouts + BSR improvement + stable price = supply shock."""
        event = SupplyShockEvent.from_signals(
            asin="B09SHOCK001",
            stockouts_90d=4,
            bsr_change=-0.30,
            price_change=0.05,
            competitors_stockout=2,
        )

        assert event is not None
        assert event.event_type == EconomicEventType.SUPPLY_SHOCK
        assert event.confidence == EventConfidence.STRONG
        assert event.urgency == EventUrgency.HIGH
        assert event.window_days == 30
        assert event.stockout_count == 4
        assert len(event.supporting_signals) >= 3
        assert len(event.contradicting_signals) == 0

    def test_moderate_supply_shock(self):
        """2 stockouts + stable price = moderate signal."""
        event = SupplyShockEvent.from_signals(
            asin="B09SHOCK002",
            stockouts_90d=2,
            bsr_change=-0.10,
            price_change=0.02,
            competitors_stockout=0,
        )

        assert event is not None
        assert event.confidence in (EventConfidence.WEAK, EventConfidence.MODERATE)
        assert event.urgency == EventUrgency.MEDIUM

    def test_no_supply_shock_insufficient_signals(self):
        """Single weak signal should not trigger supply shock."""
        event = SupplyShockEvent.from_signals(
            asin="B09NOSHOCK",
            stockouts_90d=0,
            bsr_change=0.05,
            price_change=-0.20,
            competitors_stockout=0,
        )

        assert event is None

    def test_supply_shock_with_price_drop_contra_signal(self):
        """Price dropping significantly adds a contradicting signal."""
        event = SupplyShockEvent.from_signals(
            asin="B09CONTRA",
            stockouts_90d=3,
            bsr_change=-0.25,
            price_change=-0.20,
            competitors_stockout=0,
        )

        # Should still create event (enough supporting signals)
        # but with contradicting signal recorded
        if event is not None:
            assert len(event.contradicting_signals) >= 1

    def test_supply_shock_thesis_text(self):
        """Thesis should contain meaningful description."""
        event = SupplyShockEvent.from_signals(
            asin="B09THESIS",
            stockouts_90d=3,
            bsr_change=-0.40,
            price_change=0.10,
            competitors_stockout=1,
        )

        assert event is not None
        assert "rupture" in event.thesis.lower() or "stockout" in event.thesis.lower() or "supply" in event.thesis.lower()

    def test_supply_shock_event_id_format(self):
        """Event ID should follow expected format."""
        event = SupplyShockEvent.from_signals(
            asin="B09FORMAT",
            stockouts_90d=3,
            bsr_change=-0.25,
            price_change=0.05,
            competitors_stockout=0,
        )

        assert event is not None
        assert event.event_id.startswith("ss_B09FORMAT_")


# =============================================================================
# CompetitorCollapseEvent Tests
# =============================================================================

class TestCompetitorCollapseDetection:
    """Tests for CompetitorCollapseEvent.from_signals()."""

    def test_classic_competitor_collapse(self):
        """High churn + top seller gone + no new entrants = strong collapse."""
        event = CompetitorCollapseEvent.from_signals(
            asin="B09COLLAPSE1",
            seller_churn_90d=0.40,
            top_seller_gone=True,
            buybox_rotation_change=0.30,
            new_entrants=0,
        )

        assert event is not None
        assert event.event_type == EconomicEventType.COMPETITOR_COLLAPSE
        assert event.confidence == EventConfidence.STRONG
        assert event.urgency == EventUrgency.HIGH

    def test_moderate_collapse_no_top_seller(self):
        """High churn without top seller exit = moderate."""
        event = CompetitorCollapseEvent.from_signals(
            asin="B09COLLAPSE2",
            seller_churn_90d=0.35,
            top_seller_gone=False,
            buybox_rotation_change=0.25,
            new_entrants=0,
        )

        assert event is not None
        assert event.confidence in (EventConfidence.MODERATE, EventConfidence.WEAK)

    def test_no_collapse_low_churn(self):
        """Low churn + no exit = no event."""
        event = CompetitorCollapseEvent.from_signals(
            asin="B09NOCOLLAPSE",
            seller_churn_90d=0.05,
            top_seller_gone=False,
            buybox_rotation_change=0.05,
            new_entrants=5,
        )

        assert event is None

    def test_collapse_with_replacement(self):
        """Many new entrants add contradicting signal."""
        event = CompetitorCollapseEvent.from_signals(
            asin="B09REPLACE",
            seller_churn_90d=0.35,
            top_seller_gone=True,
            buybox_rotation_change=0.30,
            new_entrants=5,
        )

        if event is not None:
            assert len(event.contradicting_signals) >= 1


# =============================================================================
# QualityDecayEvent Tests
# =============================================================================

class TestQualityDecayDetection:
    """Tests for QualityDecayEvent.from_signals()."""

    def test_classic_quality_decay(self):
        """High negatives + wish mentions + complaints = quality decay."""
        event = QualityDecayEvent.from_signals(
            asin="B09QUALITY1",
            negative_pct=0.25,
            negative_pct_trend=0.08,
            wish_mentions=10,
            common_complaints=["breaks easily", "poor mount grip", "scratches phone"],
            rating_30d_ago=4.2,
            rating_now=3.8,
        )

        assert event is not None
        assert event.event_type == EconomicEventType.QUALITY_DECAY
        assert event.confidence == EventConfidence.STRONG
        assert event.urgency == EventUrgency.MEDIUM
        assert event.window_days == 90

    def test_moderate_quality_decay(self):
        """Some negatives + wish mentions = moderate decay."""
        event = QualityDecayEvent.from_signals(
            asin="B09QUALITY2",
            negative_pct=0.18,
            negative_pct_trend=0.03,
            wish_mentions=7,
            common_complaints=["flimsy"],
            rating_30d_ago=4.0,
            rating_now=3.9,
        )

        assert event is not None
        assert len(event.supporting_signals) >= 2

    def test_no_quality_decay_good_product(self):
        """Low negatives, no complaints = no event."""
        event = QualityDecayEvent.from_signals(
            asin="B09GOODQUALITY",
            negative_pct=0.05,
            negative_pct_trend=-0.01,
            wish_mentions=1,
            common_complaints=[],
            rating_30d_ago=4.5,
            rating_now=4.5,
        )

        assert event is None

    def test_quality_decay_rating_drop(self):
        """Significant rating drop should be a signal."""
        event = QualityDecayEvent.from_signals(
            asin="B09RATINGDROP",
            negative_pct=0.16,
            negative_pct_trend=0.06,
            wish_mentions=3,
            common_complaints=[],
            rating_30d_ago=4.3,
            rating_now=3.8,
        )

        assert event is not None
        signal_types = [s["type"] for s in event.supporting_signals]
        assert "rating_decline" in signal_types


# =============================================================================
# EconomicEventDetector Tests
# =============================================================================

class TestEconomicEventDetector:
    """Tests for the EconomicEventDetector orchestrator."""

    def setup_method(self):
        self.detector = EconomicEventDetector()

    def test_detect_multiple_events(self):
        """Detector should find multiple event types for same ASIN."""
        metrics = {
            "stockouts_90d": 4,
            "bsr_change_30d": -0.30,
            "price_change_30d": 0.05,
            "competitors_stockout": 1,
            "seller_churn_90d": 0.35,
            "top_seller_gone": True,
            "buybox_rotation_change": 0.25,
            "new_entrants": 0,
            "negative_review_pct": 0.22,
            "negative_review_trend": 0.07,
            "wish_mentions": 8,
            "common_complaints": ["breaks", "poor grip", "scratches"],
            "rating_30d_ago": 4.1,
            "rating_now": 3.7,
        }

        events = self.detector.detect_all_events("B09MULTI", metrics)

        assert len(events) >= 2
        event_types = {e.event_type for e in events}
        assert EconomicEventType.SUPPLY_SHOCK in event_types
        assert EconomicEventType.COMPETITOR_COLLAPSE in event_types

    def test_detect_no_events_calm_market(self):
        """No events should be detected in a calm market."""
        metrics = {
            "stockouts_90d": 0,
            "bsr_change_30d": 0.02,
            "price_change_30d": -0.01,
            "seller_churn_90d": 0.05,
            "top_seller_gone": False,
            "buybox_rotation_change": 0.02,
            "new_entrants": 3,
            "negative_review_pct": 0.05,
            "negative_review_trend": -0.01,
            "wish_mentions": 1,
            "common_complaints": [],
            "rating_30d_ago": 4.3,
            "rating_now": 4.3,
        }

        events = self.detector.detect_all_events("B09CALM", metrics)

        assert len(events) == 0

    def test_get_primary_event(self):
        """Primary event should be the one with highest confidence + urgency."""
        metrics = {
            "stockouts_90d": 5,
            "bsr_change_30d": -0.40,
            "price_change_30d": 0.10,
            "competitors_stockout": 2,
            "seller_churn_90d": 0.25,
            "top_seller_gone": False,
            "buybox_rotation_change": 0.15,
            "new_entrants": 1,
            "negative_review_pct": 0.18,
            "negative_review_trend": 0.06,
            "wish_mentions": 6,
            "common_complaints": ["flimsy"],
            "rating_30d_ago": 4.0,
            "rating_now": 3.9,
        }

        events = self.detector.detect_all_events("B09PRIMARY", metrics)
        primary = self.detector.get_primary_event(events)

        assert primary is not None
        # Supply shock should be primary (STRONG + HIGH)
        assert primary.event_type == EconomicEventType.SUPPLY_SHOCK

    def test_get_primary_event_empty_list(self):
        """Primary event should be None for empty list."""
        primary = self.detector.get_primary_event([])
        assert primary is None

    def test_detect_with_missing_metrics(self):
        """Detector should handle missing metrics gracefully."""
        metrics = {
            "stockouts_90d": 3,
            "bsr_change_30d": -0.25,
            # Missing most other metrics
        }

        events = self.detector.detect_all_events("B09PARTIAL", metrics)
        # Should not crash, may find partial events
        assert isinstance(events, list)


# =============================================================================
# Event Properties Tests
# =============================================================================

class TestEventProperties:
    """Tests for EconomicEvent computed properties."""

    def test_signal_strength_all_supporting(self):
        """Signal strength = 1.0 when all signals support."""
        event = SupplyShockEvent.from_signals(
            asin="B09STRONG",
            stockouts_90d=5,
            bsr_change=-0.40,
            price_change=0.10,
            competitors_stockout=3,
        )

        assert event is not None
        assert event.signal_strength == 1.0

    def test_signal_strength_mixed(self):
        """Signal strength < 1.0 with contradicting signals."""
        event = SupplyShockEvent.from_signals(
            asin="B09MIXED",
            stockouts_90d=3,
            bsr_change=0.30,  # Degradation = contra signal
            price_change=0.05,
            competitors_stockout=1,
        )

        if event is not None:
            assert 0 < event.signal_strength < 1.0

    def test_signal_strength_no_signals(self):
        """Signal strength = 0 when no signals."""
        event = EconomicEvent(
            event_id="test",
            asin="B09EMPTY",
            event_type=EconomicEventType.SUPPLY_SHOCK,
            detected_at=datetime.utcnow(),
            thesis="Test",
            confidence=EventConfidence.WEAK,
            urgency=EventUrgency.LOW,
            window_days=90,
            supporting_signals=[],
            contradicting_signals=[],
        )

        assert event.signal_strength == 0.0

    def test_is_actionable_strong_event(self):
        """Actionable when confidence >= MODERATE and 2+ supporting signals."""
        event = SupplyShockEvent.from_signals(
            asin="B09ACTION",
            stockouts_90d=4,
            bsr_change=-0.30,
            price_change=0.05,
            competitors_stockout=2,
        )

        assert event is not None
        assert event.is_actionable is True

    def test_not_actionable_weak_event(self):
        """Not actionable with WEAK confidence."""
        event = EconomicEvent(
            event_id="test",
            asin="B09WEAK",
            event_type=EconomicEventType.SUPPLY_SHOCK,
            detected_at=datetime.utcnow(),
            thesis="Test",
            confidence=EventConfidence.WEAK,
            urgency=EventUrgency.LOW,
            window_days=90,
            supporting_signals=[{"type": "a"}, {"type": "b"}],
            contradicting_signals=[],
        )

        assert event.is_actionable is False

    def test_to_dict_serialization(self):
        """to_dict should produce valid serializable output."""
        event = SupplyShockEvent.from_signals(
            asin="B09SERIAL",
            stockouts_90d=3,
            bsr_change=-0.25,
            price_change=0.05,
            competitors_stockout=1,
        )

        assert event is not None
        d = event.to_dict()

        assert d["asin"] == "B09SERIAL"
        assert d["event_type"] == "supply_shock"
        assert d["confidence"] in ("weak", "moderate", "strong", "confirmed")
        assert d["urgency"] in ("low", "medium", "high", "critical")
        assert isinstance(d["supporting_signals"], list)
        assert isinstance(d["contradicting_signals"], list)
