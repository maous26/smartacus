"""
RAG Retriever
=============

2-stage retrieval:
1. Filter by metadata (doc_type, domain, marketplace, etc.)
2. Vector similarity search

Returns structured results with citations.
"""

import logging
import os
from typing import List, Optional, Dict, Any
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor

from .models import (
    RAGSearchResult,
    RAGSearchFilters,
    RAGCitation,
    DocType,
    Domain,
)
from .embedder import RAGEmbedder

logger = logging.getLogger(__name__)


class RAGRetriever:
    """
    Retrieves relevant chunks from the RAG knowledge base.

    Uses 2-stage retrieval:
    1. SQL filtering by metadata
    2. Vector similarity with pgvector
    """

    def __init__(
        self,
        embedder: Optional[RAGEmbedder] = None,
        db_url: Optional[str] = None,
    ):
        self.embedder = embedder or RAGEmbedder()
        self.db_url = db_url or os.getenv("DATABASE_URL")

        if not self.db_url:
            raise ValueError("DATABASE_URL required for RAG retriever")

    def _get_connection(self):
        """Get database connection."""
        return psycopg2.connect(self.db_url)

    def search(
        self,
        query: str,
        filters: Optional[RAGSearchFilters] = None,
        k: int = 5,
    ) -> List[RAGSearchResult]:
        """
        Search for relevant chunks.

        Args:
            query: Search query text
            filters: Optional filters for doc_type, domain, etc.
            k: Number of results to return

        Returns:
            List of RAGSearchResult ordered by similarity
        """
        # Generate query embedding
        query_embedding = self.embedder.embed_query(query)

        # Build filter conditions
        filters = filters or RAGSearchFilters()

        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Use the rag_search function
                cur.execute("""
                    SELECT * FROM rag_search(
                        %s::vector,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                """, (
                    query_embedding,
                    [dt.value for dt in filters.doc_types] if filters.doc_types else None,
                    [d.value for d in filters.domains] if filters.domains else None,
                    filters.marketplace,
                    filters.category,
                    filters.language,
                    k,
                ))

                rows = cur.fetchall()

        results = []
        for row in rows:
            result = RAGSearchResult(
                chunk_id=row['chunk_id'],
                document_id=row['document_id'],
                content=row['content'],
                context_header=row['context_header'],
                doc_type=DocType(row['doc_type']),
                domain=Domain(row['domain']),
                similarity=float(row['similarity']),
                metadata=row['metadata'] or {},
            )
            results.append(result)

        logger.info(f"RAG search returned {len(results)} results for query: {query[:50]}...")
        return results

    def search_for_agent(
        self,
        query: str,
        agent_type: str,
        k: int = 5,
    ) -> List[RAGSearchResult]:
        """
        Search with agent-specific filter presets.

        Args:
            query: Search query
            agent_type: discovery, analyst, sourcing, or negotiator
            k: Number of results

        Returns:
            List of RAGSearchResult
        """
        # Agent-specific filter mapping
        agent_filters = {
            "discovery": RAGSearchFilters(
                doc_types=[DocType.RULES, DocType.MEMORY],
                domains=[Domain.ANALYSIS, Domain.COMPLIANCE, Domain.GENERAL],
            ),
            "analyst": RAGSearchFilters(
                doc_types=[DocType.RULES, DocType.MEMORY],
                domains=[Domain.ANALYSIS, Domain.PRICING, Domain.REVIEWS, Domain.COMPLIANCE],
            ),
            "sourcing": RAGSearchFilters(
                doc_types=[DocType.OPS, DocType.TEMPLATES, DocType.RULES],
                domains=[Domain.SOURCING, Domain.QC, Domain.SHIPPING],
            ),
            "negotiator": RAGSearchFilters(
                doc_types=[DocType.OPS, DocType.TEMPLATES],
                domains=[Domain.NEGOTIATION, Domain.SOURCING],
            ),
        }

        filters = agent_filters.get(agent_type.lower(), RAGSearchFilters())
        return self.search(query, filters, k)

    def get_chunk(self, chunk_id: UUID) -> Optional[RAGSearchResult]:
        """
        Get a specific chunk by ID.
        """
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        c.id AS chunk_id,
                        c.document_id,
                        c.content,
                        c.context_header,
                        c.doc_type,
                        c.domain,
                        c.metadata,
                        d.title AS document_title
                    FROM rag_chunks c
                    JOIN rag_documents d ON c.document_id = d.id
                    WHERE c.id = %s
                """, (str(chunk_id),))

                row = cur.fetchone()

        if not row:
            return None

        return RAGSearchResult(
            chunk_id=row['chunk_id'],
            document_id=row['document_id'],
            content=row['content'],
            context_header=row['context_header'],
            doc_type=DocType(row['doc_type']),
            domain=Domain(row['domain']),
            similarity=1.0,  # N/A for direct fetch
            metadata=row['metadata'] or {},
            document_title=row['document_title'],
        )

    def cite(
        self,
        results: List[RAGSearchResult],
        session_id: str,
        agent_type: str,
        query: str,
        extracted_rules: Optional[List[str]] = None,
        recommended_template_id: Optional[UUID] = None,
    ) -> RAGCitation:
        """
        Record citation for traceability.

        Args:
            results: Search results being cited
            session_id: Agent session ID
            agent_type: Agent type
            query: Original query
            extracted_rules: Rules extracted from results
            recommended_template_id: If a template was recommended

        Returns:
            RAGCitation record
        """
        citation = RAGCitation(
            session_id=session_id,
            agent_type=agent_type,
            query_text=query,
            chunk_ids=[r.chunk_id for r in results],
            similarity_scores=[r.similarity for r in results],
            extracted_rules=extracted_rules or [],
            recommended_template_id=recommended_template_id,
        )

        # Save to database
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO rag_citations (
                        session_id, agent_type, query_text,
                        chunk_ids, similarity_scores,
                        extracted_rules, recommended_template_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, created_at
                """, (
                    citation.session_id,
                    citation.agent_type,
                    citation.query_text,
                    [str(cid) for cid in citation.chunk_ids],
                    citation.similarity_scores,
                    citation.extracted_rules,
                    str(citation.recommended_template_id) if citation.recommended_template_id else None,
                ))
                row = cur.fetchone()
                citation.id = row[0]
                citation.created_at = row[1]
                conn.commit()

        logger.info(f"Recorded citation {citation.id} with {len(results)} chunks")
        return citation

    def format_context(
        self,
        results: List[RAGSearchResult],
        max_tokens: int = 2000,
    ) -> str:
        """
        Format search results as context for LLM.

        Args:
            results: Search results to format
            max_tokens: Approximate max tokens for context

        Returns:
            Formatted context string
        """
        if not results:
            return ""

        context_parts = []
        estimated_tokens = 0
        chars_per_token = 4

        for i, result in enumerate(results, 1):
            # Format each result
            part = f"""
[Source {i}] ({result.doc_type.value}/{result.domain.value}, relevance: {result.similarity:.2f})
{result.context_header}
---
{result.content}
"""
            part_tokens = len(part) // chars_per_token

            if estimated_tokens + part_tokens > max_tokens:
                break

            context_parts.append(part)
            estimated_tokens += part_tokens

        return "\n".join(context_parts)
