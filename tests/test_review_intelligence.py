"""
Tests for Smartacus Review Intelligence (Voice of Customer).

Tests the deterministic review signal extraction and insight aggregation:
- Defect extraction: keyword lexicon matching across 9 defect types
- Wish extraction: 6 regex patterns for feature requests
- Profile aggregation: severity scoring, improvement_score calculation
- Edge cases: empty reviews, no negatives, all negatives, single review

Usage:
    pytest tests/test_review_intelligence.py -v
"""

import pytest
from src.reviews.review_models import DefectSignal, FeatureRequest, ProductImprovementProfile
from src.reviews.review_signals import (
    ReviewSignalExtractor, DEFECT_LEXICON, WISH_PATTERNS,
    normalize_wish_key, group_similar_wishes,
)
from src.reviews.review_insights import ReviewInsightAggregator


# ============================================================================
# TEST DATA
# ============================================================================

def make_review(body: str, rating: float = 1.0, review_id: str = "R_TEST") -> dict:
    """Helper to create a review dict."""
    return {"review_id": review_id, "body": body, "rating": rating, "title": ""}


NEGATIVE_REVIEWS = [
    make_review("The phone mount broke after a week. Cheap plastic snapped in half.", 1.0, "R001"),
    make_review("My phone slips and falls off every time I hit a bump. Doesn't hold at all.", 1.0, "R002"),
    make_review("Phone fell and cracked my screen. The grip is terrible and loose.", 1.0, "R003"),
    make_review("Hard to install, the instructions are confusing. Suction cup failed.", 2.0, "R004"),
    make_review("Doesn't fit my phone with the case. Too small and blocks camera.", 2.0, "R005"),
    make_review("Feels cheap and flimsy. The plastic broke on the second day.", 1.0, "R006"),
    make_review("Vibrates and rattles on every bump. Very annoying noise.", 2.0, "R007"),
    make_review("Phone overheats when mounted on the windshield. Gets too hot.", 2.0, "R008"),
    make_review("Too bulky, blocks my view through the windshield.", 3.0, "R009"),
    make_review("After a month the adhesive wore off. Didn't last at all.", 2.0, "R010"),
]

POSITIVE_REVIEWS = [
    make_review("Great mount! Holds my phone perfectly on rough roads.", 5.0, "R011"),
    make_review("Best phone mount I've ever owned. Solid construction.", 5.0, "R012"),
    make_review("Easy to install and works great with MagSafe.", 4.0, "R013"),
]

WISH_REVIEWS = [
    # V1.5: diverse phrasings are fuzzy-grouped via stopword normalisation + SequenceMatcher.
    make_review("I wish it had wireless charging built in.", 3.0, "R020"),
    make_review("I wish it had wireless charging. That would be perfect.", 4.0, "R021"),
    make_review("Would be nice if it came with a cable organizer.", 3.0, "R022"),
    make_review("Would be nice if it came with a cable organizer for the car.", 4.0, "R023"),
    make_review("Should have a night mode for the LED.", 3.0, "R024"),
    make_review("Needs a better adhesive pad for textured dashboards.", 2.0, "R025"),
    make_review("Needs a better adhesive pad.", 2.0, "R026"),
    make_review("If only it worked with thicker cases too.", 3.0, "R027"),
]

ALL_REVIEWS = NEGATIVE_REVIEWS + POSITIVE_REVIEWS + WISH_REVIEWS


# ============================================================================
# DEFECT EXTRACTION TESTS
# ============================================================================

class TestDefectExtraction:
    """Tests for ReviewSignalExtractor.extract_defects()."""

    def setup_method(self):
        self.extractor = ReviewSignalExtractor()

    def test_extracts_mechanical_failure(self):
        """'broke', 'snapped' trigger mechanical_failure."""
        defects = self.extractor.extract_defects(NEGATIVE_REVIEWS)
        types = [d.defect_type for d in defects]
        assert "mechanical_failure" in types

    def test_extracts_poor_grip(self):
        """'slips', 'falls off', 'loose' trigger poor_grip."""
        defects = self.extractor.extract_defects(NEGATIVE_REVIEWS)
        types = [d.defect_type for d in defects]
        assert "poor_grip" in types

    def test_extracts_installation_issue(self):
        """'hard to install', 'confusing' trigger installation_issue."""
        defects = self.extractor.extract_defects(NEGATIVE_REVIEWS)
        types = [d.defect_type for d in defects]
        assert "installation_issue" in types

    def test_extracts_compatibility_issue(self):
        """'doesn't fit', 'too small', 'blocks camera' trigger compatibility_issue."""
        defects = self.extractor.extract_defects(NEGATIVE_REVIEWS)
        types = [d.defect_type for d in defects]
        assert "compatibility_issue" in types

    def test_extracts_material_quality(self):
        """'cheap plastic', 'feels flimsy' trigger material_quality."""
        defects = self.extractor.extract_defects(NEGATIVE_REVIEWS)
        types = [d.defect_type for d in defects]
        assert "material_quality" in types

    def test_extracts_vibration_noise(self):
        """'vibrates', 'rattles' trigger vibration_noise."""
        defects = self.extractor.extract_defects(NEGATIVE_REVIEWS)
        types = [d.defect_type for d in defects]
        assert "vibration_noise" in types

    def test_extracts_heat_issue(self):
        """'overheats', 'gets too hot' trigger heat_issue."""
        defects = self.extractor.extract_defects(NEGATIVE_REVIEWS)
        types = [d.defect_type for d in defects]
        assert "heat_issue" in types

    def test_extracts_size_fit(self):
        """'too bulky', 'blocks view' trigger size_fit."""
        defects = self.extractor.extract_defects(NEGATIVE_REVIEWS)
        types = [d.defect_type for d in defects]
        assert "size_fit" in types

    def test_extracts_durability(self):
        """'after a month', 'adhesive wore off' trigger durability."""
        defects = self.extractor.extract_defects(NEGATIVE_REVIEWS)
        types = [d.defect_type for d in defects]
        assert "durability" in types

    def test_sorted_by_severity_desc(self):
        """Defects should be sorted by severity_score descending."""
        defects = self.extractor.extract_defects(NEGATIVE_REVIEWS)
        severities = [d.severity_score for d in defects]
        assert severities == sorted(severities, reverse=True)

    def test_only_negative_reviews_analyzed(self):
        """Only reviews with rating <= 3 should be analyzed for defects."""
        defects = self.extractor.extract_defects(ALL_REVIEWS)
        for d in defects:
            assert d.negative_reviews_scanned > 0
            assert d.total_reviews_scanned == len(ALL_REVIEWS)

    def test_empty_reviews_returns_empty(self):
        """No reviews should return no defects."""
        defects = self.extractor.extract_defects([])
        assert defects == []

    def test_only_positive_reviews_returns_empty(self):
        """Only 4-5 star reviews should return no defects."""
        defects = self.extractor.extract_defects(POSITIVE_REVIEWS)
        assert defects == []

    def test_severity_score_clamped_to_1(self):
        """Severity score should never exceed 1.0."""
        defects = self.extractor.extract_defects(NEGATIVE_REVIEWS)
        for d in defects:
            assert 0.0 <= d.severity_score <= 1.0

    def test_frequency_counts_correctly(self):
        """Frequency should match the number of reviews mentioning the defect."""
        reviews = [
            make_review("broke", 1.0, "R1"),
            make_review("broke again", 1.0, "R2"),
            make_review("snapped", 1.0, "R3"),
        ]
        defects = self.extractor.extract_defects(reviews)
        mech = [d for d in defects if d.defect_type == "mechanical_failure"]
        assert len(mech) == 1
        assert mech[0].frequency == 3

    def test_example_quotes_capped(self):
        """Example quotes should be capped at max_quotes (default 3)."""
        reviews = [make_review(f"broke item {i}", 1.0, f"R{i}") for i in range(10)]
        defects = self.extractor.extract_defects(reviews)
        mech = [d for d in defects if d.defect_type == "mechanical_failure"]
        assert len(mech) == 1
        assert len(mech[0].example_quotes) <= 3

    def test_severity_formula(self):
        """severity = base_weight * min(1.0, freq_rate * 2)."""
        reviews = [
            make_review("phone fell off", 1.0, "R1"),  # poor_grip
        ]
        defects = self.extractor.extract_defects(reviews)
        grip = [d for d in defects if d.defect_type == "poor_grip"]
        assert len(grip) == 1
        # freq_rate = 1/1 = 1.0, factor = min(1.0, 2.0) = 1.0
        # severity = 0.85 * 1.0 = 0.85
        assert grip[0].severity_score == 0.85


# ============================================================================
# WISH EXTRACTION TESTS
# ============================================================================

class TestWishExtraction:
    """Tests for ReviewSignalExtractor.extract_wish_patterns()."""

    def setup_method(self):
        self.extractor = ReviewSignalExtractor()

    def test_i_wish_pattern(self):
        """'I wish it had X' should be captured."""
        wishes = self.extractor.extract_wish_patterns(WISH_REVIEWS)
        features = [w.feature for w in wishes]
        assert any("wireless charging" in f for f in features)

    def test_would_be_nice_pattern(self):
        """'Would be nice if X' should be captured."""
        wishes = self.extractor.extract_wish_patterns(WISH_REVIEWS)
        features = [w.feature for w in wishes]
        assert any("cable organizer" in f for f in features)

    def test_needs_pattern(self):
        """'Needs a X' should be captured."""
        wishes = self.extractor.extract_wish_patterns(WISH_REVIEWS)
        features = [w.feature for w in wishes]
        assert any("adhesive" in f.lower() for f in features)

    def test_minimum_2_mentions(self):
        """Features mentioned only once should be filtered out."""
        reviews = [
            make_review("I wish it had a cup holder.", 3.0, "R1"),
        ]
        wishes = self.extractor.extract_wish_patterns(reviews)
        # Only 1 mention — should be empty
        assert len(wishes) == 0

    def test_2_mentions_included(self):
        """Features mentioned 2+ times should be included."""
        reviews = [
            make_review("I wish it had wireless charging.", 3.0, "R1"),
            make_review("I wish it had wireless charging.", 3.0, "R2"),
        ]
        wishes = self.extractor.extract_wish_patterns(reviews)
        assert len(wishes) >= 1

    def test_sorted_by_mentions_desc(self):
        """Wishes should be sorted by mentions descending."""
        wishes = self.extractor.extract_wish_patterns(WISH_REVIEWS)
        if len(wishes) > 1:
            mentions = [w.mentions for w in wishes]
            assert mentions == sorted(mentions, reverse=True)

    def test_short_features_filtered(self):
        """Features shorter than 5 chars should be filtered out."""
        reviews = [
            make_review("I wish it had a.", 3.0, "R1"),
            make_review("I wish it had a.", 3.0, "R2"),
        ]
        wishes = self.extractor.extract_wish_patterns(reviews)
        # "a" is too short (< 5 chars)
        assert len(wishes) == 0

    def test_empty_reviews_returns_empty(self):
        wishes = self.extractor.extract_wish_patterns([])
        assert wishes == []

    def test_source_quotes_capped(self):
        """Source quotes per wish should be capped at max_quotes."""
        reviews = [make_review("I wish it had wireless charging.", 3.0, f"R{i}") for i in range(10)]
        wishes = self.extractor.extract_wish_patterns(reviews)
        for w in wishes:
            assert len(w.source_quotes) <= 3

    def test_diverse_phrasings_grouped(self):
        """V1.5: similar phrasings should be grouped via fuzzy matching."""
        reviews = [
            make_review("I wish it had wireless charging built in.", 3.0, "R1"),
            make_review("I wish it had wireless charging. That would be perfect.", 4.0, "R2"),
        ]
        wishes = self.extractor.extract_wish_patterns(reviews)
        # Both should merge into one wish about wireless charging
        assert len(wishes) >= 1
        assert any("wireless charging" in w.feature for w in wishes)
        merged = [w for w in wishes if "wireless charging" in w.feature][0]
        assert merged.mentions == 2

    def test_adhesive_pad_variants_grouped(self):
        """V1.5: 'adhesive pad for X' + 'adhesive pad' should merge."""
        reviews = [
            make_review("Needs a better adhesive pad for textured dashboards.", 2.0, "R1"),
            make_review("Needs a better adhesive pad.", 2.0, "R2"),
        ]
        wishes = self.extractor.extract_wish_patterns(reviews)
        assert len(wishes) >= 1
        assert any("adhesive" in w.feature for w in wishes)

    def test_cable_organizer_variants_grouped(self):
        """V1.5: 'cable organizer' + 'cable organizer for the car' should merge."""
        reviews = [
            make_review("Would be nice if it came with a cable organizer.", 3.0, "R1"),
            make_review("Would be nice if it came with a cable organizer for the car.", 4.0, "R2"),
        ]
        wishes = self.extractor.extract_wish_patterns(reviews)
        assert len(wishes) >= 1
        assert any("cable organizer" in w.feature for w in wishes)


# ============================================================================
# WISH NORMALISATION TESTS
# ============================================================================

class TestWishNormalisation:
    """Tests for V1.5/V1.6 wish normalisation utilities."""

    def test_stopword_removal(self):
        """Stopwords should be stripped from wish text."""
        assert normalize_wish_key("it came with a cable organizer") == "cable organizer"

    def test_lowercase(self):
        assert normalize_wish_key("Wireless Charging") == "wireless charging"

    def test_punctuation_stripped(self):
        assert normalize_wish_key("wireless charging!") == "wireless charging"

    def test_empty_after_stopwords(self):
        """All-stopword text should return empty string."""
        assert normalize_wish_key("it had a") == ""

    def test_short_words_stripped(self):
        """Single-character words should be removed."""
        assert normalize_wish_key("a b c wireless") == "wireless"

    def test_group_similar_exact_match(self):
        """Identical normalized keys should merge."""
        hits = {
            "wireless charging built in": {"count": 1, "quotes": ["q1"]},
            "wireless charging": {"count": 1, "quotes": ["q2"]},
        }
        grouped = group_similar_wishes(hits)
        # Both normalize to "wireless charging", so they merge
        assert len(grouped) == 1
        key = list(grouped.keys())[0]
        assert grouped[key]["count"] == 2

    def test_group_similar_fuzzy_match(self):
        """Similar (but not identical) normalized keys should merge."""
        hits = {
            "better adhesive pad for textured dashboards": {"count": 1, "quotes": ["q1"]},
            "better adhesive pad": {"count": 1, "quotes": ["q2"]},
        }
        grouped = group_similar_wishes(hits)
        assert len(grouped) == 1
        key = list(grouped.keys())[0]
        assert grouped[key]["count"] == 2

    def test_group_dissimilar_not_merged(self):
        """Very different wishes should NOT merge."""
        hits = {
            "wireless charging": {"count": 2, "quotes": ["q1"]},
            "night mode for led": {"count": 2, "quotes": ["q2"]},
        }
        grouped = group_similar_wishes(hits)
        assert len(grouped) == 2

    def test_canonical_key_most_frequent(self):
        """Canonical key should prefer the most frequent original phrasing."""
        hits = {
            "wireless charging": {"count": 3, "quotes": []},
            "wireless charging built in": {"count": 1, "quotes": []},
        }
        grouped = group_similar_wishes(hits)
        assert len(grouped) == 1
        key = list(grouped.keys())[0]
        assert key == "wireless charging"

    def test_canonical_key_most_informative_on_tie(self):
        """On count tie, canonical = most informative (longest normalized)."""
        hits = {
            "better adhesive pad for textured dashboards": {"count": 1, "quotes": []},
            "better adhesive pad": {"count": 1, "quotes": []},
        }
        grouped = group_similar_wishes(hits)
        assert len(grouped) == 1
        key = list(grouped.keys())[0]
        # "better adhesive pad textured dashboards" (5 tokens) > "better adhesive pad" (3 tokens)
        assert key == "better adhesive pad for textured dashboards"

    def test_token_overlap_guard(self):
        """Wishes with no shared tokens should NOT merge even if ratio >= threshold."""
        hits = {
            "wireless charging": {"count": 2, "quotes": ["q1"]},
            "adhesive disc": {"count": 2, "quotes": ["q2"]},
        }
        grouped = group_similar_wishes(hits)
        assert len(grouped) == 2

    def test_quotes_capped_after_merge(self):
        """Merged group should have at most 3 quotes."""
        hits = {
            "wireless charging built in": {"count": 1, "quotes": ["q1", "q2"]},
            "wireless charging": {"count": 1, "quotes": ["q3", "q4"]},
        }
        grouped = group_similar_wishes(hits)
        key = list(grouped.keys())[0]
        assert len(grouped[key]["quotes"]) <= 3

    def test_niche_stopwords_stripped(self):
        """Niche words like 'phone', 'mount', 'car' should be stripped."""
        assert normalize_wish_key("phone mount wireless charging") == "wireless charging"
        assert normalize_wish_key("car dashboard holder clip") == "clip"

    def test_helpful_votes_aggregated(self):
        """Helpful votes should be summed across merged wishes."""
        hits = {
            "wireless charging built in": {"count": 1, "quotes": [], "helpful_votes": 10},
            "wireless charging": {"count": 1, "quotes": [], "helpful_votes": 25},
        }
        grouped = group_similar_wishes(hits)
        key = list(grouped.keys())[0]
        assert grouped[key]["helpful_votes"] == 35

    def test_wish_strength_includes_helpful(self):
        """wish_strength should be mentions + log1p(helpful_votes)."""
        import math
        reviews = [
            {"body": "I wish it had wireless charging.", "rating": 3.0, "helpful_votes": 20},
            {"body": "I wish it had wireless charging.", "rating": 3.0, "helpful_votes": 30},
        ]
        extractor = ReviewSignalExtractor()
        wishes = extractor.extract_wish_patterns(reviews)
        assert len(wishes) == 1
        w = wishes[0]
        assert w.helpful_votes == 50
        expected = 2 + math.log1p(50)
        assert abs(w.wish_strength - round(expected, 2)) < 0.01

    def test_wish_strength_sorting(self):
        """Wishes should be sorted by wish_strength, not just mentions."""
        reviews = [
            # 2 mentions, high helpful (40 total)
            {"body": "I wish it had wireless charging.", "rating": 3.0, "helpful_votes": 20},
            {"body": "I wish it had wireless charging.", "rating": 3.0, "helpful_votes": 20},
            # 2 mentions, low helpful (0 total)
            {"body": "I wish it had a night light.", "rating": 3.0, "helpful_votes": 0},
            {"body": "I wish it had a night light.", "rating": 3.0, "helpful_votes": 0},
        ]
        extractor = ReviewSignalExtractor()
        wishes = extractor.extract_wish_patterns(reviews)
        assert len(wishes) == 2
        # wireless charging should rank first due to higher helpful_votes
        assert "wireless charging" in wishes[0].feature


# ============================================================================
# AGGREGATION TESTS
# ============================================================================

class TestReviewInsightAggregator:
    """Tests for ReviewInsightAggregator.build_profile()."""

    def setup_method(self):
        self.aggregator = ReviewInsightAggregator()
        self.extractor = ReviewSignalExtractor()

    def test_empty_signals_returns_zero_score(self):
        """No defects and no wishes = improvement_score 0.0."""
        profile = self.aggregator.build_profile("B0TEST", [], [], 10, 3)
        assert profile.improvement_score == 0.0
        assert profile.dominant_pain is None
        assert profile.reviews_ready is True

    def test_no_reviews_returns_not_ready(self):
        """Zero reviews_analyzed = reviews_ready False."""
        profile = self.aggregator.build_profile("B0TEST", [], [], 0, 0)
        assert profile.reviews_ready is False

    def test_defects_produce_positive_score(self):
        """Defects should produce improvement_score > 0."""
        defects = self.extractor.extract_defects(NEGATIVE_REVIEWS)
        profile = self.aggregator.build_profile(
            "B0TEST", defects, [], len(ALL_REVIEWS), len(NEGATIVE_REVIEWS)
        )
        assert profile.improvement_score > 0.0

    def test_score_range_0_to_1(self):
        """improvement_score should be in [0.0, 1.0]."""
        defects = self.extractor.extract_defects(NEGATIVE_REVIEWS)
        wishes = self.extractor.extract_wish_patterns(WISH_REVIEWS)
        profile = self.aggregator.build_profile(
            "B0TEST", defects, wishes, len(ALL_REVIEWS), len(NEGATIVE_REVIEWS)
        )
        assert 0.0 <= profile.improvement_score <= 1.0

    def test_dominant_pain_is_highest_severity(self):
        """dominant_pain should be the defect type with highest severity."""
        defects = self.extractor.extract_defects(NEGATIVE_REVIEWS)
        profile = self.aggregator.build_profile(
            "B0TEST", defects, [], len(ALL_REVIEWS), len(NEGATIVE_REVIEWS)
        )
        assert profile.dominant_pain == defects[0].defect_type

    def test_top_defects_capped_at_5(self):
        """Profile should contain at most 5 defects."""
        defects = self.extractor.extract_defects(NEGATIVE_REVIEWS)
        profile = self.aggregator.build_profile(
            "B0TEST", defects, [], len(ALL_REVIEWS), len(NEGATIVE_REVIEWS)
        )
        assert len(profile.top_defects) <= 5

    def test_wish_bonus_adds_to_score(self):
        """Wishes with 3+ mentions add +0.1 each (capped at 0.2)."""
        defects = self.extractor.extract_defects(NEGATIVE_REVIEWS)

        # Build profile without wishes
        profile_no_wish = self.aggregator.build_profile(
            "B0TEST", defects, [], len(ALL_REVIEWS), len(NEGATIVE_REVIEWS)
        )

        # Build profile with wishes that have 3+ mentions
        wishes_with_mentions = [
            FeatureRequest(feature="wireless charging", mentions=5, confidence=0.8, source_quotes=[]),
            FeatureRequest(feature="cable organizer", mentions=3, confidence=0.6, source_quotes=[]),
        ]
        profile_with_wish = self.aggregator.build_profile(
            "B0TEST", defects, wishes_with_mentions, len(ALL_REVIEWS), len(NEGATIVE_REVIEWS)
        )

        assert profile_with_wish.improvement_score >= profile_no_wish.improvement_score

    def test_wish_bonus_capped_at_02(self):
        """Wish bonus should not exceed 0.2 even with many wishes."""
        wishes = [
            FeatureRequest(feature=f"feature_{i}", mentions=10, confidence=1.0, source_quotes=[])
            for i in range(10)
        ]
        profile = self.aggregator.build_profile("B0TEST", [], wishes, 100, 50)
        assert profile.improvement_score <= 0.2

    def test_missing_features_capped_at_5(self):
        """Profile should contain at most 5 missing_features."""
        wishes = [
            FeatureRequest(feature=f"feature_{i}", mentions=5, confidence=0.8, source_quotes=[])
            for i in range(10)
        ]
        defects = self.extractor.extract_defects(NEGATIVE_REVIEWS)
        profile = self.aggregator.build_profile(
            "B0TEST", defects, wishes, len(ALL_REVIEWS), len(NEGATIVE_REVIEWS)
        )
        assert len(profile.missing_features) <= 5


# ============================================================================
# LEXICON COVERAGE TESTS
# ============================================================================

class TestLexiconCoverage:
    """Ensure the defect lexicon covers all 9 defect types."""

    def test_lexicon_has_9_types(self):
        assert len(DEFECT_LEXICON) == 9

    def test_all_types_have_keywords(self):
        for dtype, (keywords, weight) in DEFECT_LEXICON.items():
            assert len(keywords) > 0, f"{dtype} has no keywords"
            assert 0.0 < weight <= 1.0, f"{dtype} weight {weight} out of range"

    def test_wish_patterns_count(self):
        assert len(WISH_PATTERNS) == 6


# ============================================================================
# MODEL TESTS
# ============================================================================

class TestReviewModels:
    """Tests for review data models."""

    def test_defect_signal_frequency_rate(self):
        """frequency_rate = frequency / negative_reviews_scanned."""
        d = DefectSignal(
            defect_type="poor_grip", frequency=5, severity_score=0.8,
            example_quotes=[], total_reviews_scanned=20, negative_reviews_scanned=10
        )
        assert d.frequency_rate == 0.5

    def test_defect_signal_frequency_rate_zero_negatives(self):
        d = DefectSignal(
            defect_type="poor_grip", frequency=5, severity_score=0.8,
            example_quotes=[], total_reviews_scanned=20, negative_reviews_scanned=0
        )
        assert d.frequency_rate == 0.0

    def test_profile_has_actionable_insights(self):
        profile = ProductImprovementProfile(
            asin="B0TEST",
            top_defects=[DefectSignal("poor_grip", 5, 0.8, [], 20, 10)],
            missing_features=[],
            dominant_pain="poor_grip",
            improvement_score=0.6,
            reviews_analyzed=20,
            negative_reviews_analyzed=10,
            reviews_ready=True,
        )
        assert profile.has_actionable_insights is True

    def test_profile_no_insights_when_low_score(self):
        profile = ProductImprovementProfile(
            asin="B0TEST",
            top_defects=[],
            missing_features=[],
            dominant_pain=None,
            improvement_score=0.1,
            reviews_analyzed=20,
            negative_reviews_analyzed=10,
            reviews_ready=True,
        )
        assert profile.has_actionable_insights is False

    def test_profile_thesis_fragment(self):
        profile = ProductImprovementProfile(
            asin="B0TEST",
            top_defects=[DefectSignal("poor_grip", 5, 0.8, [], 20, 10)],
            missing_features=[],
            dominant_pain="poor_grip",
            improvement_score=0.6,
            reviews_analyzed=20,
            negative_reviews_analyzed=10,
            reviews_ready=True,
        )
        thesis = profile.to_thesis_fragment()
        assert "poor_grip" in thesis
        assert "50%" in thesis  # 5/10 = 50%
