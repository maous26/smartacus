"""
RAG Ingestion Pipeline
======================

Pipeline for ingesting documents into the RAG knowledge base.

Flow:
1. Normalize document
2. Chunk into pieces
3. Generate embeddings
4. Upsert to database (with deduplication)
"""

import logging
import os
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from datetime import date

import psycopg2
from psycopg2.extras import execute_values

from .models import RAGDocument, RAGChunk, DocType, Domain
from .chunker import RAGChunker, ChunkConfig
from .embedder import RAGEmbedder

logger = logging.getLogger(__name__)


class RAGIngestion:
    """
    Ingestion pipeline for RAG knowledge base.

    Handles:
    - Document creation
    - Chunking
    - Embedding generation
    - Database upsert with deduplication
    """

    def __init__(
        self,
        embedder: Optional[RAGEmbedder] = None,
        chunker: Optional[RAGChunker] = None,
        db_url: Optional[str] = None,
    ):
        self.embedder = embedder or RAGEmbedder()
        self.chunker = chunker or RAGChunker()
        self.db_url = db_url or os.getenv("DATABASE_URL")

        if not self.db_url:
            raise ValueError("DATABASE_URL required for RAG ingestion")

        self._documents_ingested = 0
        self._chunks_created = 0
        self._chunks_skipped = 0  # Duplicates

    def _get_connection(self):
        """Get database connection."""
        return psycopg2.connect(self.db_url)

    def ingest_document(self, document: RAGDocument) -> UUID:
        """
        Ingest a single document.

        Args:
            document: RAGDocument to ingest

        Returns:
            UUID of the created document
        """
        # Generate ID if not provided
        if document.id is None:
            document.id = uuid4()

        # Insert document
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO rag_documents (
                        id, doc_type, domain, title, description,
                        source, source_type, marketplace, category, language,
                        effective_date, expiry_date, confidence,
                        run_id, asin, metadata
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                """, (
                    str(document.id),
                    document.doc_type.value,
                    document.domain.value,
                    document.title,
                    document.description,
                    document.source,
                    document.source_type,
                    document.marketplace,
                    document.category,
                    document.language,
                    document.effective_date or date.today(),
                    document.expiry_date,
                    document.confidence,
                    document.run_id,
                    document.asin,
                    psycopg2.extras.Json(document.metadata),
                ))
                conn.commit()

        # Chunk the document
        chunks = self.chunker.chunk_document(document)

        if not chunks:
            logger.warning(f"No chunks generated for document {document.id}")
            return document.id

        # Generate embeddings
        chunk_contents = [c.content for c in chunks]
        embeddings = self.embedder.embed_batch(chunk_contents)

        # Attach embeddings to chunks
        for chunk, emb_result in zip(chunks, embeddings):
            chunk.embedding = emb_result.embedding
            chunk.token_count = emb_result.token_count

        # Insert chunks (with deduplication)
        self._insert_chunks(chunks)

        self._documents_ingested += 1
        logger.info(f"Ingested document {document.id}: {document.title}")

        return document.id

    def _insert_chunks(self, chunks: List[RAGChunk]) -> int:
        """
        Insert chunks with deduplication.

        Returns:
            Number of chunks actually inserted (excluding duplicates)
        """
        if not chunks:
            return 0

        inserted = 0
        skipped = 0

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                for chunk in chunks:
                    try:
                        # Generate chunk ID
                        chunk_id = uuid4()

                        cur.execute("""
                            INSERT INTO rag_chunks (
                                id, document_id, chunk_index,
                                content, content_hash, context_header,
                                embedding, token_count,
                                doc_type, domain, marketplace, category, language,
                                metadata
                            ) VALUES (
                                %s, %s, %s,
                                %s, %s, %s,
                                %s, %s,
                                %s, %s, %s, %s, %s,
                                %s
                            )
                            ON CONFLICT (content_hash) DO NOTHING
                        """, (
                            str(chunk_id),
                            str(chunk.document_id),
                            chunk.chunk_index,
                            chunk.content,
                            chunk.content_hash,
                            chunk.context_header,
                            chunk.embedding,
                            chunk.token_count,
                            chunk.doc_type.value,
                            chunk.domain.value,
                            chunk.marketplace,
                            chunk.category,
                            chunk.language,
                            psycopg2.extras.Json(chunk.metadata),
                        ))

                        if cur.rowcount > 0:
                            inserted += 1
                        else:
                            skipped += 1

                    except psycopg2.errors.UniqueViolation:
                        skipped += 1
                        conn.rollback()
                        continue

                conn.commit()

        self._chunks_created += inserted
        self._chunks_skipped += skipped

        if skipped > 0:
            logger.debug(f"Skipped {skipped} duplicate chunks")

        return inserted

    def ingest_batch(self, documents: List[RAGDocument]) -> List[UUID]:
        """
        Ingest multiple documents.

        Args:
            documents: List of RAGDocument to ingest

        Returns:
            List of created document UUIDs
        """
        return [self.ingest_document(doc) for doc in documents]

    def ingest_text(
        self,
        title: str,
        content: str,
        doc_type: DocType,
        domain: Domain,
        **kwargs,
    ) -> UUID:
        """
        Convenience method to ingest raw text.

        Args:
            title: Document title
            content: Document content
            doc_type: Document type
            domain: Knowledge domain
            **kwargs: Additional RAGDocument fields

        Returns:
            UUID of created document
        """
        document = RAGDocument(
            title=title,
            content=content,
            doc_type=doc_type,
            domain=domain,
            **kwargs,
        )
        return self.ingest_document(document)

    def ingest_thesis(
        self,
        asin: str,
        thesis_data: Dict[str, Any],
        run_id: Optional[str] = None,
    ) -> UUID:
        """
        Ingest a generated thesis into memory corpus.

        Args:
            asin: Product ASIN
            thesis_data: Thesis data from ThesisGenerator
            run_id: Pipeline run ID

        Returns:
            UUID of created document
        """
        # Format thesis as document
        content = f"""
# Economic Thesis: {thesis_data.get('headline', 'Unknown')}

## Summary
{thesis_data.get('thesis', '')}

## Reasoning
{chr(10).join('- ' + r for r in thesis_data.get('reasoning', []))}

## Risks
{chr(10).join('- ' + r for r in thesis_data.get('risks', []))}

## Next Steps
{chr(10).join('- ' + s for s in thesis_data.get('next_steps', []))}

## Metrics
- Confidence: {thesis_data.get('confidence', 'unknown')}
- Action: {thesis_data.get('action', 'unknown')}
- Urgency: {thesis_data.get('urgency', 'unknown')}
- Estimated Monthly Profit: ${thesis_data.get('estimated_monthly_profit', 0)}
"""

        document = RAGDocument(
            title=f"Thesis: {thesis_data.get('headline', asin)}",
            content=content,
            doc_type=DocType.MEMORY,
            domain=Domain.ANALYSIS,
            source=f"thesis_generator:{asin}",
            source_type="auto",
            asin=asin,
            run_id=run_id,
            confidence=0.9,  # Auto-generated
            expiry_date=None,  # Keep indefinitely
            metadata={
                "thesis_confidence": thesis_data.get('confidence'),
                "thesis_urgency": thesis_data.get('urgency'),
            },
        )

        return self.ingest_document(document)

    def delete_document(self, document_id: UUID) -> bool:
        """
        Soft-delete a document (sets is_active=FALSE).

        Chunks are kept for historical reference.
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE rag_documents
                    SET is_active = FALSE, updated_at = NOW()
                    WHERE id = %s
                """, (str(document_id),))
                conn.commit()
                return cur.rowcount > 0

    def hard_delete_document(self, document_id: UUID) -> bool:
        """
        Permanently delete a document and all its chunks.
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM rag_documents WHERE id = %s
                """, (str(document_id),))
                conn.commit()
                return cur.rowcount > 0

    @property
    def stats(self) -> Dict[str, int]:
        """Get ingestion statistics."""
        return {
            "documents_ingested": self._documents_ingested,
            "chunks_created": self._chunks_created,
            "chunks_skipped": self._chunks_skipped,
            "embedding_tokens": self.embedder.total_tokens,
            "embedding_cost_usd": self.embedder.estimated_cost,
        }
