"""
Smartacus RAG Module
====================

Retrieval-Augmented Generation system for knowledge-enhanced agents.

4 Corpus:
- Rules: Amazon policies, compliance, SOP
- Ops: Sourcing, QC, incoterms, negotiation, checklists
- Templates: RFQ, follow-ups, clauses, scripts
- Memory: Historical theses, analyses, decisions

Architecture:
- pgvector for vector storage
- OpenAI text-embedding-3-small for embeddings
- 2-stage retrieval: metadata filter → vector similarity
"""

from .embedder import RAGEmbedder
from .chunker import RAGChunker
from .retriever import RAGRetriever
from .ingestion import RAGIngestion
from .models import (
    RAGDocument,
    RAGChunk,
    RAGSearchResult,
    RAGCitation,
    DocType,
    Domain,
)

__all__ = [
    "RAGEmbedder",
    "RAGChunker",
    "RAGRetriever",
    "RAGIngestion",
    "RAGDocument",
    "RAGChunk",
    "RAGSearchResult",
    "RAGCitation",
    "DocType",
    "Domain",
]
