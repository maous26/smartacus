"""
Product Spec Data Models
=========================

Structured outputs for the spec generation pipeline.
Maps to the product_spec_bundles DB table (migration 007).
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class OEMRequirement:
    """A single OEM requirement line derived from a defect or feature."""
    source_bloc: str             # "A" (defect fix) or "B" (feature add)
    source_type: str             # defect_type or feature name
    requirement: str             # e.g. "Ball-joint mechanism rated 50,000 cycles min"
    material_spec: Optional[str] # e.g. "PC+ABS blend, UL94-V0 rated"
    tolerance: Optional[str]     # e.g. "+/- 0.5mm on all mounting points"
    priority: str                # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    severity_score: float        # from DefectSignal or wish_strength (normalized)


@dataclass
class OEMSpec:
    """Complete OEM Product Specification document."""
    asin: str
    generated_at: datetime
    product_type: str = "Car Phone Mount"
    bloc_a_requirements: List[OEMRequirement] = field(default_factory=list)
    bloc_b_requirements: List[OEMRequirement] = field(default_factory=list)
    general_materials: List[str] = field(default_factory=list)
    accessories_included: List[str] = field(default_factory=list)
    packaging_notes: List[str] = field(default_factory=list)
    rendered_text: str = ""

    @property
    def total_requirements(self) -> int:
        return len(self.bloc_a_requirements) + len(self.bloc_b_requirements)


@dataclass
class QCTestItem:
    """A single QC test line."""
    test_category: str        # vibration, cycles, thermal, surface, load, compatibility
    test_name: str
    method: str
    pass_criterion: str
    source_defect: Optional[str]
    priority: str             # MANDATORY, RECOMMENDED


@dataclass
class QCChecklist:
    """Complete QC Checklist document."""
    asin: str
    generated_at: datetime
    tests: List[QCTestItem] = field(default_factory=list)
    rendered_text: str = ""

    @property
    def mandatory_count(self) -> int:
        return sum(1 for t in self.tests if t.priority == "MANDATORY")


@dataclass
class RFQMessage:
    """Ready-to-send RFQ message for supplier outreach."""
    asin: str
    generated_at: datetime
    subject_line: str = ""
    body_text: str = ""
    key_requirements_summary: List[str] = field(default_factory=list)
    target_moq: str = "500-1000 units"


@dataclass
class ProductSpecBundle:
    """Container for all three deliverables for one ASIN."""
    asin: str
    generated_at: datetime
    oem_spec: OEMSpec
    qc_checklist: QCChecklist
    rfq_message: RFQMessage
    improvement_score: float
    reviews_analyzed: int
    version: str = "1.8"
    mapping_version: str = "1.8.0"
    inputs_hash: str = ""

    def to_dict(self) -> dict:
        """Serialize to dict for JSON storage in DB."""
        return {
            "asin": self.asin,
            "generated_at": self.generated_at.isoformat(),
            "version": self.version,
            "mapping_version": self.mapping_version,
            "inputs_hash": self.inputs_hash,
            "improvement_score": self.improvement_score,
            "reviews_analyzed": self.reviews_analyzed,
            "oem_spec": {
                "bloc_a": [
                    {"source": r.source_type, "requirement": r.requirement,
                     "material": r.material_spec, "tolerance": r.tolerance,
                     "priority": r.priority}
                    for r in self.oem_spec.bloc_a_requirements
                ],
                "bloc_b": [
                    {"source": r.source_type, "requirement": r.requirement,
                     "material": r.material_spec, "tolerance": r.tolerance,
                     "priority": r.priority}
                    for r in self.oem_spec.bloc_b_requirements
                ],
                "general_materials": self.oem_spec.general_materials,
                "accessories": self.oem_spec.accessories_included,
                "rendered_text": self.oem_spec.rendered_text,
            },
            "qc_checklist": {
                "tests": [
                    {"category": t.test_category, "name": t.test_name,
                     "method": t.method, "pass_criterion": t.pass_criterion,
                     "priority": t.priority}
                    for t in self.qc_checklist.tests
                ],
                "rendered_text": self.qc_checklist.rendered_text,
            },
            "rfq_message": {
                "subject": self.rfq_message.subject_line,
                "body": self.rfq_message.body_text,
                "key_requirements": self.rfq_message.key_requirements_summary,
            },
        }
