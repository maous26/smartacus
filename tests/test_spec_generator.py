"""
Tests for Product Spec Generator (V1.8)
========================================

Coverage:
- Spec mappings: all defect types mapped, all have requirements + QC tests
- Spec generator: Bloc A/B generation, sorting, QC dedup, rendering, serialization
- Feature matching: substring match, unmatched features
- Integration: reviews → profile → spec bundle

Usage:
    pytest tests/test_spec_generator.py -v
"""

import json
import pytest
from src.reviews.review_models import DefectSignal, FeatureRequest, ProductImprovementProfile
from src.specs.spec_mappings import (
    DEFECT_TO_SPEC, FEATURE_TO_SPEC, MAPPING_VERSION, severity_to_priority,
    DEFAULT_GENERAL_MATERIALS, DEFAULT_ACCESSORIES,
)
from src.specs.spec_generator import SpecGenerator
from src.specs.spec_models import ProductSpecBundle


# ============================================================================
# TEST HELPERS
# ============================================================================

def make_defect(
    defect_type: str = "poor_grip",
    frequency: int = 5,
    severity: float = 0.5,
) -> DefectSignal:
    return DefectSignal(
        defect_type=defect_type,
        frequency=frequency,
        severity_score=severity,
        example_quotes=["quote1"],
        total_reviews_scanned=20,
        negative_reviews_scanned=12,
    )


def make_feature(
    feature: str = "wireless charging built in",
    mentions: int = 3,
    strength: float = 5.0,
) -> FeatureRequest:
    return FeatureRequest(
        feature=feature,
        mentions=mentions,
        confidence=0.8,
        wish_strength=strength,
    )


def make_profile(
    defects=None, features=None, score=0.5,
) -> ProductImprovementProfile:
    return ProductImprovementProfile(
        asin="B0TEST001",
        top_defects=defects or [],
        missing_features=features or [],
        dominant_pain=defects[0].defect_type if defects else None,
        improvement_score=score,
        reviews_analyzed=20,
        negative_reviews_analyzed=12,
        reviews_ready=True,
    )


# ============================================================================
# SPEC MAPPINGS TESTS
# ============================================================================

class TestSpecMappings:
    """Tests for spec_mappings.py constants."""

    def test_all_defect_types_mapped(self):
        """Every defect type from the lexicon has a DEFECT_TO_SPEC entry."""
        expected = {
            "mechanical_failure", "poor_grip", "installation_issue",
            "compatibility_issue", "material_quality", "vibration_noise",
            "heat_issue", "size_fit", "durability",
        }
        assert set(DEFECT_TO_SPEC.keys()) == expected

    def test_all_mappings_have_requirements(self):
        """Each defect mapping has at least 1 requirement tuple."""
        for dtype, mapping in DEFECT_TO_SPEC.items():
            assert len(mapping["requirements"]) >= 1, f"{dtype} has no requirements"

    def test_all_mappings_have_qc_tests(self):
        """Each defect mapping has at least 1 QC test."""
        for dtype, mapping in DEFECT_TO_SPEC.items():
            assert len(mapping["qc_tests"]) >= 1, f"{dtype} has no QC tests"

    def test_requirement_tuples_have_3_elements(self):
        """Each requirement is a (requirement, material, tolerance) tuple."""
        for dtype, mapping in DEFECT_TO_SPEC.items():
            for req in mapping["requirements"]:
                assert len(req) == 3, f"{dtype} requirement wrong format: {req}"

    def test_qc_test_tuples_have_4_elements(self):
        """Each QC test is a (category, name, method, criterion) tuple."""
        for dtype, mapping in DEFECT_TO_SPEC.items():
            for test in mapping["qc_tests"]:
                assert len(test) == 4, f"{dtype} QC test wrong format: {test}"

    def test_feature_mappings_have_requirement(self):
        """Each feature mapping has a non-empty requirement string."""
        for key, spec in FEATURE_TO_SPEC.items():
            assert spec["requirement"], f"Feature '{key}' has empty requirement"

    def test_severity_to_priority_critical(self):
        assert severity_to_priority(0.8) == "CRITICAL"
        assert severity_to_priority(0.9) == "CRITICAL"
        assert severity_to_priority(1.0) == "CRITICAL"

    def test_severity_to_priority_high(self):
        assert severity_to_priority(0.6) == "HIGH"
        assert severity_to_priority(0.79) == "HIGH"

    def test_severity_to_priority_medium(self):
        assert severity_to_priority(0.4) == "MEDIUM"
        assert severity_to_priority(0.59) == "MEDIUM"

    def test_severity_to_priority_low(self):
        assert severity_to_priority(0.1) == "LOW"
        assert severity_to_priority(0.39) == "LOW"


# ============================================================================
# SPEC GENERATOR TESTS
# ============================================================================

class TestSpecGenerator:
    """Tests for SpecGenerator.generate()."""

    def setup_method(self):
        self.gen = SpecGenerator()

    def test_generate_with_defects(self):
        """Profile with defects produces Bloc A requirements."""
        profile = make_profile(defects=[
            make_defect("poor_grip", 5, 0.85),
            make_defect("mechanical_failure", 3, 0.72),
        ])
        bundle = self.gen.generate(profile)
        assert len(bundle.oem_spec.bloc_a_requirements) >= 2
        assert all(r.source_bloc == "A" for r in bundle.oem_spec.bloc_a_requirements)

    def test_generate_with_features(self):
        """Profile with features produces Bloc B requirements."""
        profile = make_profile(features=[
            make_feature("wireless charging built in", 3, 5.0),
        ])
        bundle = self.gen.generate(profile)
        assert len(bundle.oem_spec.bloc_b_requirements) >= 1
        assert all(r.source_bloc == "B" for r in bundle.oem_spec.bloc_b_requirements)

    def test_generate_empty_profile(self):
        """Empty profile produces valid but empty bundle."""
        profile = make_profile(defects=[], features=[], score=0.0)
        bundle = self.gen.generate(profile)
        assert bundle.oem_spec.total_requirements == 0
        assert len(bundle.qc_checklist.tests) == 0
        assert bundle.rfq_message.body_text != ""  # RFQ still renders

    def test_bloc_a_sorted_by_severity(self):
        """Bloc A requirements respect severity DESC order."""
        profile = make_profile(defects=[
            make_defect("material_quality", 5, 0.3),
            make_defect("poor_grip", 3, 0.85),
        ])
        bundle = self.gen.generate(profile)
        reqs = bundle.oem_spec.bloc_a_requirements
        # poor_grip (0.85) requirements should come before material_quality (0.3)
        poor_grip_idx = next(i for i, r in enumerate(reqs) if r.source_type == "poor_grip")
        material_idx = next(i for i, r in enumerate(reqs) if r.source_type == "material_quality")
        assert poor_grip_idx < material_idx

    def test_bloc_b_sorted_by_wish_strength(self):
        """Bloc B requirements respect wish_strength DESC order."""
        profile = make_profile(features=[
            make_feature("cable organizer", 2, 2.0),
            make_feature("wireless charging built in", 3, 5.0),
        ])
        bundle = self.gen.generate(profile)
        reqs = bundle.oem_spec.bloc_b_requirements
        assert len(reqs) == 2
        assert "wireless charging" in reqs[0].source_type.lower()

    def test_qc_tests_deduplicated(self):
        """Duplicate QC test names are removed."""
        profile = make_profile(defects=[
            make_defect("poor_grip", 5, 0.8),
            make_defect("poor_grip", 3, 0.6),  # same type → same tests
        ])
        bundle = self.gen.generate(profile)
        names = [t.test_name for t in bundle.qc_checklist.tests]
        assert len(names) == len(set(names)), "Duplicate QC tests found"

    def test_qc_mandatory_count(self):
        """CRITICAL/HIGH defects produce MANDATORY QC tests."""
        profile = make_profile(defects=[
            make_defect("poor_grip", 5, 0.85),  # priority_base = CRITICAL
        ])
        bundle = self.gen.generate(profile)
        assert bundle.qc_checklist.mandatory_count >= 1

    def test_rfq_contains_key_requirements(self):
        """RFQ body includes key requirements text."""
        profile = make_profile(defects=[
            make_defect("poor_grip", 5, 0.85),
        ])
        bundle = self.gen.generate(profile)
        assert "KEY REQUIREMENTS:" in bundle.rfq_message.body_text
        assert len(bundle.rfq_message.key_requirements_summary) >= 1

    def test_rendered_text_not_empty(self):
        """All rendered_text fields are non-empty when defects present."""
        profile = make_profile(defects=[make_defect("poor_grip", 5, 0.85)])
        bundle = self.gen.generate(profile)
        assert bundle.oem_spec.rendered_text
        assert bundle.qc_checklist.rendered_text
        assert bundle.rfq_message.body_text

    def test_to_dict_serialization(self):
        """ProductSpecBundle.to_dict() produces valid JSON."""
        profile = make_profile(
            defects=[make_defect("poor_grip", 5, 0.85)],
            features=[make_feature("wireless charging built in", 3, 5.0)],
        )
        bundle = self.gen.generate(profile)
        d = bundle.to_dict()
        # Must be JSON-serializable
        serialized = json.dumps(d)
        assert len(serialized) > 100
        # Verify structure
        assert "oem_spec" in d
        assert "qc_checklist" in d
        assert "rfq_message" in d
        assert len(d["oem_spec"]["bloc_a"]) >= 1
        assert len(d["oem_spec"]["bloc_b"]) >= 1

    def test_feature_matching_substring(self):
        """Feature 'wireless charging built in' matches 'wireless charging' key."""
        profile = make_profile(features=[
            make_feature("wireless charging built in", 3, 5.0),
        ])
        bundle = self.gen.generate(profile)
        assert len(bundle.oem_spec.bloc_b_requirements) == 1
        assert "Qi" in bundle.oem_spec.bloc_b_requirements[0].requirement

    def test_unmatched_feature_skipped(self):
        """Feature with no mapping match produces no Bloc B entry."""
        profile = make_profile(features=[
            make_feature("telepathy control module", 2, 3.0),
        ])
        bundle = self.gen.generate(profile)
        assert len(bundle.oem_spec.bloc_b_requirements) == 0

    def test_general_materials_included(self):
        """Default general materials are always present."""
        profile = make_profile()
        bundle = self.gen.generate(profile)
        assert len(bundle.oem_spec.general_materials) == len(DEFAULT_GENERAL_MATERIALS)

    def test_accessories_include_feature_extras(self):
        """Feature accessories are appended to defaults."""
        profile = make_profile(features=[
            make_feature("wireless charging built in", 3, 5.0),
        ])
        bundle = self.gen.generate(profile)
        # Default 3 + wireless charging adds 1 (USB-C cable)
        assert len(bundle.oem_spec.accessories_included) > len(DEFAULT_ACCESSORIES)

    def test_feature_qc_test_added(self):
        """Feature with a qc_test adds it to the checklist."""
        profile = make_profile(features=[
            make_feature("wireless charging built in", 3, 5.0),
        ])
        bundle = self.gen.generate(profile)
        test_names = [t.test_name for t in bundle.qc_checklist.tests]
        assert any("charging" in n.lower() for n in test_names)

    def test_rfq_subject_line_format(self):
        """RFQ subject line contains spec and test counts."""
        profile = make_profile(defects=[make_defect("poor_grip", 5, 0.85)])
        bundle = self.gen.generate(profile)
        assert "RFQ" in bundle.rfq_message.subject_line
        assert "specs" in bundle.rfq_message.subject_line
        assert "QC tests" in bundle.rfq_message.subject_line

    def test_mapping_version_set(self):
        """Bundle contains the current MAPPING_VERSION."""
        profile = make_profile(defects=[make_defect("poor_grip", 5, 0.85)])
        bundle = self.gen.generate(profile)
        assert bundle.mapping_version == MAPPING_VERSION

    def test_inputs_hash_deterministic(self):
        """Same inputs produce the same hash."""
        profile = make_profile(defects=[make_defect("poor_grip", 5, 0.85)])
        b1 = self.gen.generate(profile)
        b2 = self.gen.generate(profile)
        assert b1.inputs_hash == b2.inputs_hash
        assert len(b1.inputs_hash) == 16  # sha256[:16]

    def test_inputs_hash_changes_on_different_inputs(self):
        """Different inputs produce different hashes."""
        p1 = make_profile(defects=[make_defect("poor_grip", 5, 0.85)])
        p2 = make_profile(defects=[make_defect("poor_grip", 8, 0.90)])
        b1 = self.gen.generate(p1)
        b2 = self.gen.generate(p2)
        assert b1.inputs_hash != b2.inputs_hash

    def test_to_dict_includes_versioning(self):
        """to_dict() includes mapping_version and inputs_hash."""
        profile = make_profile(defects=[make_defect("poor_grip", 5, 0.85)])
        bundle = self.gen.generate(profile)
        d = bundle.to_dict()
        assert d["mapping_version"] == MAPPING_VERSION
        assert len(d["inputs_hash"]) == 16


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestSpecGeneratorIntegration:
    """Integration tests with ReviewSignalExtractor pipeline."""

    def test_end_to_end_from_reviews(self):
        """Full pipeline: reviews → defects → profile → spec bundle."""
        from src.reviews.review_signals import ReviewSignalExtractor
        from src.reviews.review_insights import ReviewInsightAggregator

        reviews = [
            {"body": "The arm broke after a month. Cheap plastic.", "rating": 1.0},
            {"body": "Phone keeps falling off on bumps. Slips.", "rating": 2.0},
            {"body": "Phone fell and cracked screen. Doesn't hold.", "rating": 1.0},
            {"body": "Broke after a week. Snapped right off.", "rating": 1.0},
            {"body": "I wish it had wireless charging.", "rating": 3.0},
            {"body": "I wish it had wireless charging built in.", "rating": 4.0},
            {"body": "Great mount, works perfectly!", "rating": 5.0},
        ]

        extractor = ReviewSignalExtractor()
        defects = extractor.extract_defects(reviews)
        wishes = extractor.extract_wish_patterns(reviews)

        neg = sum(1 for r in reviews if r.get("rating", 5) <= 3)
        aggregator = ReviewInsightAggregator()
        profile = aggregator.build_profile("B0INTTEST", defects, wishes, len(reviews), neg)

        gen = SpecGenerator()
        bundle = gen.generate(profile)

        assert bundle.oem_spec.total_requirements > 0
        assert len(bundle.qc_checklist.tests) > 0
        assert "Dear Supplier" in bundle.rfq_message.body_text
        assert bundle.version == "1.8"

    def test_roundtrip_bundle_json(self):
        """to_dict() output can be serialized to JSON and back."""
        profile = make_profile(
            defects=[make_defect("poor_grip", 5, 0.85)],
            features=[make_feature("wireless charging built in", 3, 5.0)],
        )
        gen = SpecGenerator()
        bundle = gen.generate(profile)

        d = bundle.to_dict()
        serialized = json.dumps(d)
        loaded = json.loads(serialized)

        assert loaded["asin"] == "B0TEST001"
        assert loaded["version"] == "1.8"
        assert loaded["mapping_version"] == MAPPING_VERSION
        assert len(loaded["inputs_hash"]) == 16
        assert len(loaded["oem_spec"]["bloc_a"]) > 0
        assert len(loaded["qc_checklist"]["tests"]) > 0
