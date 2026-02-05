"""
Product Spec Generator (Deterministic)
=======================================

Generates OEM specs, QC checklists, and RFQ messages from
ProductImprovementProfile data using template-based rendering.

No LLM calls. 100% deterministic. Niche-specific for Car Phone Mounts.

Usage:
    generator = SpecGenerator()
    bundle = generator.generate(profile)
    generator.save_bundle(conn, bundle, run_id)
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Optional, List

from ..reviews.review_models import (
    ProductImprovementProfile,
    DefectSignal,
    FeatureRequest,
)
from .spec_models import (
    OEMSpec, OEMRequirement, QCChecklist, QCTestItem,
    RFQMessage, ProductSpecBundle,
)
from .spec_mappings import (
    DEFECT_TO_SPEC, FEATURE_TO_SPEC, MAPPING_VERSION,
    DEFAULT_GENERAL_MATERIALS, DEFAULT_ACCESSORIES, DEFAULT_PACKAGING_NOTES,
    severity_to_priority,
)

logger = logging.getLogger(__name__)


class SpecGenerator:
    """
    Deterministic product spec generator.

    Consumes a ProductImprovementProfile and produces a ProductSpecBundle
    containing OEM spec, QC checklist, and RFQ message.
    """

    @staticmethod
    def _compute_inputs_hash(profile: ProductImprovementProfile) -> str:
        """Hash the profile inputs for reproducibility tracking."""
        data = {
            "defects": [
                {"type": d.defect_type, "freq": d.frequency, "sev": round(d.severity_score, 4)}
                for d in sorted(profile.top_defects, key=lambda d: d.defect_type)
            ],
            "features": [
                {"feature": f.feature, "mentions": f.mentions, "strength": round(f.wish_strength, 4)}
                for f in sorted(profile.missing_features, key=lambda f: f.feature)
            ],
        }
        raw = json.dumps(data, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def generate(self, profile: ProductImprovementProfile) -> ProductSpecBundle:
        """Generate all three deliverables from an improvement profile."""
        now = datetime.now(tz=None)

        oem_spec = self._build_oem_spec(profile, now)
        qc_checklist = self._build_qc_checklist(profile, now)
        rfq_message = self._build_rfq_message(profile, oem_spec, qc_checklist, now)

        bundle = ProductSpecBundle(
            asin=profile.asin,
            generated_at=now,
            oem_spec=oem_spec,
            qc_checklist=qc_checklist,
            rfq_message=rfq_message,
            improvement_score=profile.improvement_score,
            reviews_analyzed=profile.reviews_analyzed,
            mapping_version=MAPPING_VERSION,
            inputs_hash=self._compute_inputs_hash(profile),
        )

        logger.info(
            f"Generated spec bundle for {profile.asin}: "
            f"{oem_spec.total_requirements} requirements, "
            f"{len(qc_checklist.tests)} QC tests"
        )

        return bundle

    # -----------------------------------------------------------------
    # OEM Spec
    # -----------------------------------------------------------------

    def _build_oem_spec(
        self, profile: ProductImprovementProfile, now: datetime,
    ) -> OEMSpec:
        bloc_a = self._build_bloc_a(profile.top_defects)
        bloc_b = self._build_bloc_b(profile.missing_features)

        extra_accessories = []
        for feat in profile.missing_features:
            spec = self._match_feature(feat.feature)
            if spec and spec.get("accessory"):
                extra_accessories.append(spec["accessory"])

        oem = OEMSpec(
            asin=profile.asin,
            generated_at=now,
            bloc_a_requirements=bloc_a,
            bloc_b_requirements=bloc_b,
            general_materials=list(DEFAULT_GENERAL_MATERIALS),
            accessories_included=DEFAULT_ACCESSORIES + extra_accessories,
            packaging_notes=list(DEFAULT_PACKAGING_NOTES),
        )
        oem.rendered_text = self._render_oem_spec(oem, profile)
        return oem

    def _build_bloc_a(self, defects: List[DefectSignal]) -> List[OEMRequirement]:
        """Bloc A: Fix defects — sorted by severity DESC, frequency DESC."""
        requirements = []
        sorted_defects = sorted(
            defects,
            key=lambda d: (d.severity_score, d.frequency),
            reverse=True,
        )
        for defect in sorted_defects:
            mapping = DEFECT_TO_SPEC.get(defect.defect_type)
            if not mapping:
                continue
            priority = severity_to_priority(defect.severity_score)
            for req_text, material, tolerance in mapping["requirements"]:
                requirements.append(OEMRequirement(
                    source_bloc="A",
                    source_type=defect.defect_type,
                    requirement=req_text,
                    material_spec=material,
                    tolerance=tolerance,
                    priority=priority,
                    severity_score=defect.severity_score,
                ))
        return requirements

    def _build_bloc_b(self, features: List[FeatureRequest]) -> List[OEMRequirement]:
        """Bloc B: Add features — sorted by wish_strength DESC."""
        requirements = []
        sorted_features = sorted(
            features,
            key=lambda f: f.wish_strength,
            reverse=True,
        )
        for feat in sorted_features:
            spec = self._match_feature(feat.feature)
            if not spec:
                continue
            norm_strength = min(1.0, feat.wish_strength / 10.0)
            requirements.append(OEMRequirement(
                source_bloc="B",
                source_type=feat.feature,
                requirement=spec["requirement"],
                material_spec=spec.get("material"),
                tolerance=spec.get("tolerance"),
                priority="HIGH" if norm_strength > 0.6 else "MEDIUM",
                severity_score=norm_strength,
            ))
        return requirements

    def _match_feature(self, feature_text: str) -> Optional[dict]:
        """Match a feature request to a FEATURE_TO_SPEC entry via substring."""
        feature_lower = feature_text.lower()
        for keyword, spec in FEATURE_TO_SPEC.items():
            if keyword in feature_lower:
                return spec
        return None

    def _render_oem_spec(
        self, spec: OEMSpec, profile: ProductImprovementProfile,
    ) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append("OEM PRODUCT SPECIFICATION -- CAR PHONE MOUNT")
        lines.append(f"ASIN: {spec.asin}")
        lines.append(f"Generated: {spec.generated_at.strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append(f"Improvement Score: {profile.improvement_score:.1%}")
        lines.append(f"Based on: {profile.reviews_analyzed} reviews analyzed")
        lines.append("=" * 60)
        lines.append("")

        lines.append("BLOC A -- DEFECT CORRECTIONS (Priority Order)")
        lines.append("-" * 50)
        if spec.bloc_a_requirements:
            for i, req in enumerate(spec.bloc_a_requirements, 1):
                lines.append(f"  A{i}. [{req.priority}] {req.requirement}")
                lines.append(f"       Source: {req.source_type} (severity: {req.severity_score:.2f})")
                if req.material_spec:
                    lines.append(f"       Material: {req.material_spec}")
                if req.tolerance:
                    lines.append(f"       Tolerance: {req.tolerance}")
                lines.append("")
        else:
            lines.append("  No critical defects identified.")
            lines.append("")

        lines.append("BLOC B -- FEATURE ENHANCEMENTS (Demand Order)")
        lines.append("-" * 50)
        if spec.bloc_b_requirements:
            for i, req in enumerate(spec.bloc_b_requirements, 1):
                lines.append(f"  B{i}. [{req.priority}] {req.requirement}")
                lines.append(f"       Feature: {req.source_type}")
                if req.material_spec:
                    lines.append(f"       Material: {req.material_spec}")
                if req.tolerance:
                    lines.append(f"       Tolerance: {req.tolerance}")
                lines.append("")
        else:
            lines.append("  No feature enhancements identified.")
            lines.append("")

        lines.append("GENERAL MATERIALS")
        lines.append("-" * 50)
        for mat in spec.general_materials:
            lines.append(f"  - {mat}")
        lines.append("")

        lines.append("ACCESSORIES INCLUDED")
        lines.append("-" * 50)
        for acc in spec.accessories_included:
            lines.append(f"  - {acc}")
        lines.append("")

        lines.append("PACKAGING")
        lines.append("-" * 50)
        for note in spec.packaging_notes:
            lines.append(f"  - {note}")

        return "\n".join(lines)

    # -----------------------------------------------------------------
    # QC Checklist
    # -----------------------------------------------------------------

    def _build_qc_checklist(
        self, profile: ProductImprovementProfile, now: datetime,
    ) -> QCChecklist:
        tests = []

        for defect in profile.top_defects:
            mapping = DEFECT_TO_SPEC.get(defect.defect_type)
            if not mapping:
                continue
            priority_base = mapping["priority_base"]
            for cat, name, method, criterion in mapping["qc_tests"]:
                tests.append(QCTestItem(
                    test_category=cat,
                    test_name=name,
                    method=method,
                    pass_criterion=criterion,
                    source_defect=defect.defect_type,
                    priority="MANDATORY" if priority_base in ("CRITICAL", "HIGH") else "RECOMMENDED",
                ))

        for feat in profile.missing_features:
            spec = self._match_feature(feat.feature)
            if spec and spec.get("qc_test"):
                cat, name, method, criterion = spec["qc_test"]
                tests.append(QCTestItem(
                    test_category=cat,
                    test_name=name,
                    method=method,
                    pass_criterion=criterion,
                    source_defect=None,
                    priority="RECOMMENDED",
                ))

        # Deduplicate by test_name
        seen = set()
        unique_tests = []
        for t in tests:
            if t.test_name not in seen:
                seen.add(t.test_name)
                unique_tests.append(t)

        checklist = QCChecklist(asin=profile.asin, generated_at=now, tests=unique_tests)
        checklist.rendered_text = self._render_qc_checklist(checklist)
        return checklist

    def _render_qc_checklist(self, checklist: QCChecklist) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append("QC INSPECTION CHECKLIST -- CAR PHONE MOUNT")
        lines.append(f"ASIN: {checklist.asin}")
        lines.append(f"Generated: {checklist.generated_at.strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append(f"Total tests: {len(checklist.tests)} ({checklist.mandatory_count} mandatory)")
        lines.append("=" * 60)
        lines.append("")

        categories = {}
        for t in checklist.tests:
            categories.setdefault(t.test_category, []).append(t)

        category_labels = {
            "vibration": "VIBRATION & SHOCK",
            "cycles": "ENDURANCE & CYCLES",
            "thermal": "THERMAL & ENVIRONMENTAL",
            "surface": "SURFACE & VISUAL",
            "load": "LOAD & RETENTION",
            "compatibility": "COMPATIBILITY",
        }

        for cat_key, cat_tests in categories.items():
            label = category_labels.get(cat_key, cat_key.upper())
            lines.append(f"[{label}]")
            lines.append("-" * 40)
            for i, t in enumerate(cat_tests, 1):
                status = "MANDATORY" if t.priority == "MANDATORY" else "RECOMMENDED"
                lines.append(f"  {i}. {t.test_name} [{status}]")
                lines.append(f"     Method: {t.method}")
                lines.append(f"     Pass: {t.pass_criterion}")
                if t.source_defect:
                    lines.append(f"     Triggered by: {t.source_defect}")
                lines.append(f"     Result: [ ] PASS  [ ] FAIL  [ ] N/A")
                lines.append("")

        return "\n".join(lines)

    # -----------------------------------------------------------------
    # RFQ Message
    # -----------------------------------------------------------------

    def _build_rfq_message(
        self,
        profile: ProductImprovementProfile,
        oem_spec: OEMSpec,
        qc_checklist: QCChecklist,
        now: datetime,
    ) -> RFQMessage:
        all_reqs = oem_spec.bloc_a_requirements + oem_spec.bloc_b_requirements
        top_reqs = sorted(all_reqs, key=lambda r: r.severity_score, reverse=True)[:5]
        key_summary = [r.requirement for r in top_reqs]

        subject = (
            f"RFQ -- Car Phone Mount (Custom OEM) -- "
            f"{len(all_reqs)} specs, {len(qc_checklist.tests)} QC tests"
        )

        body = self._render_rfq_body(oem_spec, qc_checklist, key_summary)

        return RFQMessage(
            asin=profile.asin,
            generated_at=now,
            subject_line=subject,
            body_text=body,
            key_requirements_summary=key_summary,
        )

    def _render_rfq_body(
        self,
        oem_spec: OEMSpec,
        qc_checklist: QCChecklist,
        key_summary: List[str],
    ) -> str:
        lines = []
        lines.append("Dear Supplier,")
        lines.append("")
        lines.append("We are sourcing a custom Car Phone Mount for the Amazon US market.")
        lines.append(
            f"Our product specification includes {oem_spec.total_requirements} requirements "
            f"and {len(qc_checklist.tests)} QC test procedures "
            f"({qc_checklist.mandatory_count} mandatory)."
        )
        lines.append("")
        lines.append("KEY REQUIREMENTS:")
        for i, req in enumerate(key_summary, 1):
            lines.append(f"  {i}. {req}")
        lines.append("")
        lines.append("MATERIALS:")
        for mat in oem_spec.general_materials[:3]:
            lines.append(f"  - {mat}")
        lines.append("")
        lines.append("QC HIGHLIGHTS:")
        lines.append(f"  - {qc_checklist.mandatory_count} mandatory tests (vibration, thermal, cycles)")
        lines.append(f"  - {len(qc_checklist.tests) - qc_checklist.mandatory_count} recommended tests")
        lines.append("")
        lines.append("VOLUME: Initial order 500-1,000 units. Scaling to 3,000-5,000/month if QC passes.")
        lines.append("")
        lines.append("Please provide:")
        lines.append("  1. Unit price for MOQ 500 and MOQ 1,000")
        lines.append("  2. Sample lead time and cost")
        lines.append("  3. Production lead time for first order")
        lines.append("  4. Your QC capabilities (in-house testing equipment)")
        lines.append("  5. Certifications: FCC, CE, RoHS (required)")
        lines.append("")
        lines.append("Full technical specification and QC checklist attached.")
        lines.append("")
        lines.append("Best regards")

        return "\n".join(lines)

    # -----------------------------------------------------------------
    # DB Persistence
    # -----------------------------------------------------------------

    def save_bundle(
        self, conn, bundle: ProductSpecBundle, run_id: Optional[str] = None,
    ):
        """Save spec bundle to product_spec_bundles table."""
        try:
            bundle_json = json.dumps(bundle.to_dict())
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO product_spec_bundles (
                        asin, run_id, version,
                        oem_spec_text, qc_checklist_text, rfq_message_text,
                        bundle_json, improvement_score, reviews_analyzed,
                        total_requirements, total_qc_tests,
                        mapping_version, inputs_hash
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (asin, run_id) DO UPDATE SET
                        version = EXCLUDED.version,
                        oem_spec_text = EXCLUDED.oem_spec_text,
                        qc_checklist_text = EXCLUDED.qc_checklist_text,
                        rfq_message_text = EXCLUDED.rfq_message_text,
                        bundle_json = EXCLUDED.bundle_json,
                        improvement_score = EXCLUDED.improvement_score,
                        reviews_analyzed = EXCLUDED.reviews_analyzed,
                        total_requirements = EXCLUDED.total_requirements,
                        total_qc_tests = EXCLUDED.total_qc_tests,
                        mapping_version = EXCLUDED.mapping_version,
                        inputs_hash = EXCLUDED.inputs_hash,
                        generated_at = NOW()
                """, (
                    bundle.asin, run_id, bundle.version,
                    bundle.oem_spec.rendered_text,
                    bundle.qc_checklist.rendered_text,
                    bundle.rfq_message.body_text,
                    bundle_json,
                    bundle.improvement_score,
                    bundle.reviews_analyzed,
                    bundle.oem_spec.total_requirements,
                    len(bundle.qc_checklist.tests),
                    bundle.mapping_version,
                    bundle.inputs_hash,
                ))
                conn.commit()
                logger.info(
                    f"Saved spec bundle for {bundle.asin}: "
                    f"{bundle.oem_spec.total_requirements} reqs, "
                    f"{len(bundle.qc_checklist.tests)} tests"
                )
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save spec bundle for {bundle.asin}: {e}")
            raise

    def load_bundle_from_db(
        self, conn, asin: str, run_id: Optional[str] = None,
    ) -> Optional[dict]:
        """Load spec bundle for an ASIN. If run_id given, load that specific version."""
        with conn.cursor() as cur:
            if run_id:
                cur.execute("""
                    SELECT bundle_json, oem_spec_text, qc_checklist_text,
                           rfq_message_text, generated_at, version,
                           improvement_score, reviews_analyzed,
                           total_requirements, total_qc_tests,
                           mapping_version, inputs_hash, run_id
                    FROM product_spec_bundles
                    WHERE asin = %s AND run_id = %s
                """, (asin, run_id))
            else:
                cur.execute("""
                    SELECT bundle_json, oem_spec_text, qc_checklist_text,
                           rfq_message_text, generated_at, version,
                           improvement_score, reviews_analyzed,
                           total_requirements, total_qc_tests,
                           mapping_version, inputs_hash, run_id
                    FROM product_spec_bundles
                    WHERE asin = %s
                    ORDER BY generated_at DESC
                    LIMIT 1
                """, (asin,))
            row = cur.fetchone()

        if not row:
            return None

        return {
            "bundle": row[0],
            "oem_spec_text": row[1],
            "qc_checklist_text": row[2],
            "rfq_message_text": row[3],
            "generated_at": row[4].isoformat() if row[4] else None,
            "version": row[5],
            "improvement_score": float(row[6]) if row[6] else 0.0,
            "reviews_analyzed": row[7] or 0,
            "total_requirements": row[8] or 0,
            "total_qc_tests": row[9] or 0,
            "mapping_version": row[10] or "",
            "inputs_hash": row[11] or "",
            "run_id": str(row[12]) if row[12] else None,
        }
