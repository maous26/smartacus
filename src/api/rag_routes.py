"""
Smartacus RAG API Routes
========================

Endpoints pour la gestion de la base de connaissances RAG.
"""

import logging
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import date

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rag", tags=["RAG"])


# =============================================================================
# MODELS
# =============================================================================

class RAGSearchRequest(BaseModel):
    """Requête de recherche RAG."""
    query: str = Field(..., description="Search query")
    agent_type: Optional[str] = Field(None, description="Agent type for filtered search")
    doc_types: Optional[List[str]] = Field(None, description="Filter by doc types")
    domains: Optional[List[str]] = Field(None, description="Filter by domains")
    k: int = Field(5, description="Number of results")


class RAGSearchResult(BaseModel):
    """Résultat de recherche."""
    chunk_id: str
    document_id: str
    content: str
    context_header: Optional[str]
    doc_type: str
    domain: str
    similarity: float


class RAGSearchResponse(BaseModel):
    """Réponse de recherche."""
    query: str
    results: List[RAGSearchResult]
    formatted_context: str


class RAGIngestRequest(BaseModel):
    """Requête d'ingestion de document."""
    title: str
    content: str
    doc_type: str = Field(..., description="rules|ops|templates|memory")
    domain: str
    source: Optional[str] = None
    marketplace: str = "US"
    category: Optional[str] = None
    language: str = "en"
    expiry_days: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class RAGIngestResponse(BaseModel):
    """Réponse d'ingestion."""
    document_id: str
    title: str
    chunks_created: int


class RAGStatsResponse(BaseModel):
    """Statistiques RAG."""
    total_documents: int
    total_chunks: int
    documents_by_type: Dict[str, int]
    chunks_by_type: Dict[str, int]


# =============================================================================
# SEARCH ENDPOINT
# =============================================================================

@router.post("/search", response_model=RAGSearchResponse)
async def search_knowledge(request: RAGSearchRequest):
    """
    Recherche dans la base de connaissances RAG.

    Utilise le retrieval 2 étapes :
    1. Filtrage par metadata
    2. Similarité vectorielle
    """
    try:
        from ..rag import RAGRetriever, RAGSearchFilters, DocType, Domain

        retriever = RAGRetriever()

        # Build filters if provided
        if request.agent_type:
            results = retriever.search_for_agent(
                query=request.query,
                agent_type=request.agent_type,
                k=request.k,
            )
        else:
            filters = None
            if request.doc_types or request.domains:
                filters = RAGSearchFilters(
                    doc_types=[DocType(dt) for dt in request.doc_types] if request.doc_types else None,
                    domains=[Domain(d) for d in request.domains] if request.domains else None,
                )
            results = retriever.search(
                query=request.query,
                filters=filters,
                k=request.k,
            )

        # Format response
        formatted_context = retriever.format_context(results)

        return RAGSearchResponse(
            query=request.query,
            results=[
                RAGSearchResult(
                    chunk_id=str(r.chunk_id),
                    document_id=str(r.document_id),
                    content=r.content,
                    context_header=r.context_header,
                    doc_type=r.doc_type.value,
                    domain=r.domain.value,
                    similarity=r.similarity,
                )
                for r in results
            ],
            formatted_context=formatted_context,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=503,
            detail=f"RAG not configured: {str(e)}"
        )
    except Exception as e:
        logger.error(f"RAG search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# INGEST ENDPOINT
# =============================================================================

@router.post("/ingest", response_model=RAGIngestResponse)
async def ingest_document(request: RAGIngestRequest):
    """
    Ingère un nouveau document dans la base de connaissances.

    Le document est :
    1. Chunké (400-800 tokens)
    2. Embeddings générés
    3. Stocké avec déduplication
    """
    try:
        from ..rag import RAGIngestion, RAGDocument, DocType, Domain
        from datetime import timedelta

        ingestion = RAGIngestion()

        # Build document
        expiry_date = None
        if request.expiry_days:
            expiry_date = date.today() + timedelta(days=request.expiry_days)

        document = RAGDocument(
            title=request.title,
            content=request.content,
            doc_type=DocType(request.doc_type),
            domain=Domain(request.domain),
            source=request.source,
            marketplace=request.marketplace,
            category=request.category,
            language=request.language,
            expiry_date=expiry_date,
            metadata=request.metadata or {},
        )

        doc_id = ingestion.ingest_document(document)

        return RAGIngestResponse(
            document_id=str(doc_id),
            title=document.title,
            chunks_created=ingestion.stats["chunks_created"],
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document: {str(e)}"
        )
    except Exception as e:
        logger.error(f"RAG ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# STATS ENDPOINT
# =============================================================================

@router.get("/stats", response_model=RAGStatsResponse)
async def get_rag_stats():
    """
    Retourne les statistiques de la base de connaissances.
    """
    try:
        import os
        import psycopg2
        from psycopg2.extras import RealDictCursor

        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("DATABASE_URL not set")

        conn = psycopg2.connect(db_url)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Total documents
            cur.execute("SELECT COUNT(*) as count FROM rag_documents WHERE is_active = TRUE")
            total_docs = cur.fetchone()['count']

            # Total chunks
            cur.execute("SELECT COUNT(*) as count FROM rag_chunks")
            total_chunks = cur.fetchone()['count']

            # By type
            cur.execute("""
                SELECT doc_type, COUNT(*) as count
                FROM rag_documents WHERE is_active = TRUE
                GROUP BY doc_type
            """)
            docs_by_type = {row['doc_type']: row['count'] for row in cur.fetchall()}

            cur.execute("""
                SELECT doc_type, COUNT(*) as count
                FROM rag_chunks
                GROUP BY doc_type
            """)
            chunks_by_type = {row['doc_type']: row['count'] for row in cur.fetchall()}

        conn.close()

        return RAGStatsResponse(
            total_documents=total_docs,
            total_chunks=total_chunks,
            documents_by_type=docs_by_type,
            chunks_by_type=chunks_by_type,
        )

    except Exception as e:
        logger.error(f"RAG stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# STATUS ENDPOINT
# =============================================================================

@router.get("/status")
async def rag_status():
    """
    Vérifie le statut du système RAG.
    """
    import os

    db_configured = bool(os.getenv("DATABASE_URL"))
    openai_configured = bool(os.getenv("OPENAI_API_KEY") or os.getenv("GPT_API_KEY"))

    # Check if pgvector is available
    pgvector_available = False
    if db_configured:
        try:
            import psycopg2
            conn = psycopg2.connect(os.getenv("DATABASE_URL"))
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                pgvector_available = cur.fetchone() is not None
            conn.close()
        except Exception:
            pass

    return {
        "rag_available": db_configured and openai_configured and pgvector_available,
        "database_configured": db_configured,
        "embeddings_configured": openai_configured,
        "pgvector_available": pgvector_available,
    }
