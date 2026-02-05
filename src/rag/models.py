"""
RAG Data Models
===============

Pydantic models for RAG system.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import UUID


class DocType(str, Enum):
    """Document types for the 4 corpus."""
    RULES = "rules"          # Amazon policies, compliance, SOP
    OPS = "ops"              # Sourcing, QC, incoterms, negotiation
    TEMPLATES = "templates"  # RFQ, follow-ups, clauses, scripts
    MEMORY = "memory"        # Historical theses, analyses, decisions


class Domain(str, Enum):
    """Knowledge domains."""
    SOURCING = "sourcing"
    NEGOTIATION = "negotiation"
    COMPLIANCE = "compliance"
    ANALYSIS = "analysis"
    QC = "qc"
    SHIPPING = "shipping"
    LISTING = "listing"
    PRICING = "pricing"
    REVIEWS = "reviews"
    GENERAL = "general"


@dataclass
class RAGDocument:
    """A document in the RAG knowledge base."""
    title: str
    doc_type: DocType
    domain: Domain
    content: str  # Full content before chunking

    # Optional metadata
    id: Optional[UUID] = None
    description: Optional[str] = None
    source: Optional[str] = None
    source_type: str = "manual"
    marketplace: str = "US"
    category: Optional[str] = None
    language: str = "en"
    effective_date: Optional[date] = None
    expiry_date: Optional[date] = None
    confidence: float = 1.0
    run_id: Optional[str] = None
    asin: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.doc_type, str):
            self.doc_type = DocType(self.doc_type)
        if isinstance(self.domain, str):
            self.domain = Domain(self.domain)


@dataclass
class RAGChunk:
    """A chunk of a document with embedding."""
    document_id: UUID
    chunk_index: int
    content: str
    content_hash: str
    context_header: str

    # Inherited from document for fast filtering
    doc_type: DocType
    domain: Domain
    marketplace: str = "US"
    category: Optional[str] = None
    language: str = "en"

    # Embedding
    embedding: Optional[List[float]] = None
    token_count: Optional[int] = None

    # Optional
    id: Optional[UUID] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RAGSearchResult:
    """A search result from RAG retrieval."""
    chunk_id: UUID
    document_id: UUID
    content: str
    context_header: Optional[str]
    doc_type: DocType
    domain: Domain
    similarity: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Optionally loaded
    document_title: Optional[str] = None


@dataclass
class RAGCitation:
    """Citation record for traceability."""
    session_id: str
    agent_type: str
    query_text: str
    chunk_ids: List[UUID]
    similarity_scores: List[float]

    # Extracted info
    extracted_rules: List[str] = field(default_factory=list)
    recommended_template_id: Optional[UUID] = None

    # Auto
    id: Optional[UUID] = None
    created_at: Optional[datetime] = None


@dataclass
class RAGSearchFilters:
    """Filters for RAG search."""
    doc_types: Optional[List[DocType]] = None
    domains: Optional[List[Domain]] = None
    marketplace: Optional[str] = None
    category: Optional[str] = None
    language: str = "en"

    def to_sql_params(self) -> Dict[str, Any]:
        """Convert to SQL function parameters."""
        return {
            "p_doc_types": [dt.value for dt in self.doc_types] if self.doc_types else None,
            "p_domains": [d.value for d in self.domains] if self.domains else None,
            "p_marketplace": self.marketplace,
            "p_category": self.category,
            "p_language": self.language,
        }
