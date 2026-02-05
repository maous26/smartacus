"""
Smartacus Product Spec Generator (V1.8)
=======================================

Deterministic generation of OEM specs, QC checklists, and RFQ messages
from ProductImprovementProfile data. No LLM required.
"""

from .spec_models import OEMSpec, QCChecklist, RFQMessage, ProductSpecBundle
from .spec_generator import SpecGenerator
