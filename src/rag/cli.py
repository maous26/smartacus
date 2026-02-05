"""
RAG CLI
=======

Command-line interface for RAG management.

Usage:
    python -m src.rag.cli init        # Initialize database schema
    python -m src.rag.cli seed        # Seed initial corpus
    python -m src.rag.cli search "query"  # Test search
    python -m src.rag.cli stats       # Show statistics
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import date, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()

from src.rag.models import RAGDocument, DocType, Domain
from src.rag.ingestion import RAGIngestion
from src.rag.retriever import RAGRetriever

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def init_schema():
    """Initialize RAG database schema."""
    import psycopg2

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL not set")
        return False

    migration_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "database", "migrations", "003_rag_pgvector.sql"
    )

    if not os.path.exists(migration_path):
        logger.error(f"Migration file not found: {migration_path}")
        return False

    with open(migration_path, 'r') as f:
        migration_sql = f.read()

    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            cur.execute(migration_sql)
        conn.commit()
        conn.close()
        logger.info("RAG schema initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize schema: {e}")
        return False


def seed_corpus():
    """Seed the initial corpus."""
    from src.rag.corpus import get_all_seed_documents

    logger.info("Loading seed documents...")
    seed_docs = get_all_seed_documents()
    logger.info(f"Found {len(seed_docs)} seed documents")

    try:
        ingestion = RAGIngestion()

        for doc_data in seed_docs:
            # Calculate expiry date
            expiry_date = None
            if doc_data.get("expiry_days"):
                expiry_date = date.today() + timedelta(days=doc_data["expiry_days"])

            document = RAGDocument(
                title=doc_data["title"],
                content=doc_data["content"],
                doc_type=DocType(doc_data["doc_type"]),
                domain=Domain(doc_data["domain"]),
                source=doc_data.get("source", "seed_data"),
                source_type=doc_data.get("source_type", "manual"),
                confidence=doc_data.get("confidence", 1.0),
                expiry_date=expiry_date,
            )

            try:
                doc_id = ingestion.ingest_document(document)
                logger.info(f"Ingested: {document.title} -> {doc_id}")
            except Exception as e:
                logger.error(f"Failed to ingest '{document.title}': {e}")

        stats = ingestion.stats
        logger.info(f"""
Ingestion complete:
- Documents: {stats['documents_ingested']}
- Chunks created: {stats['chunks_created']}
- Chunks skipped (duplicates): {stats['chunks_skipped']}
- Embedding tokens: {stats['embedding_tokens']}
- Estimated cost: ${stats['embedding_cost_usd']:.4f}
""")
        return True

    except Exception as e:
        logger.error(f"Seeding failed: {e}")
        return False


def test_search(query: str, agent_type: str = "discovery", k: int = 3):
    """Test RAG search."""
    try:
        retriever = RAGRetriever()
        results = retriever.search_for_agent(query, agent_type, k)

        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print(f"Agent: {agent_type}")
        print(f"Results: {len(results)}")
        print('='*60)

        for i, r in enumerate(results, 1):
            print(f"\n[{i}] Similarity: {r.similarity:.3f}")
            print(f"    Type: {r.doc_type.value}/{r.domain.value}")
            print(f"    Context: {r.context_header}")
            print(f"    Content: {r.content[:200]}...")

        # Show formatted context
        print(f"\n{'='*60}")
        print("FORMATTED CONTEXT FOR LLM:")
        print('='*60)
        print(retriever.format_context(results))

        return True

    except Exception as e:
        logger.error(f"Search failed: {e}")
        return False


def show_stats():
    """Show RAG statistics."""
    import psycopg2
    from psycopg2.extras import RealDictCursor

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL not set")
        return False

    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Document counts by type
            cur.execute("""
                SELECT doc_type, COUNT(*) as count
                FROM rag_documents
                WHERE is_active = TRUE
                GROUP BY doc_type
            """)
            doc_counts = cur.fetchall()

            # Chunk counts by type
            cur.execute("""
                SELECT doc_type, COUNT(*) as count, SUM(token_count) as total_tokens
                FROM rag_chunks
                GROUP BY doc_type
            """)
            chunk_counts = cur.fetchall()

            # Total embeddings
            cur.execute("SELECT COUNT(*) FROM rag_chunks WHERE embedding IS NOT NULL")
            embedded_count = cur.fetchone()['count']

            # Citations
            cur.execute("SELECT COUNT(*) FROM rag_citations")
            citation_count = cur.fetchone()['count']

        conn.close()

        print(f"\n{'='*60}")
        print("RAG STATISTICS")
        print('='*60)

        print("\nDocuments by type:")
        for row in doc_counts:
            print(f"  {row['doc_type']}: {row['count']}")

        print("\nChunks by type:")
        for row in chunk_counts:
            tokens = row['total_tokens'] or 0
            print(f"  {row['doc_type']}: {row['count']} chunks ({tokens:,} tokens)")

        print(f"\nTotal embedded chunks: {embedded_count}")
        print(f"Total citations recorded: {citation_count}")

        return True

    except Exception as e:
        logger.error(f"Stats failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="RAG Knowledge Base CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Init command
    subparsers.add_parser("init", help="Initialize database schema")

    # Seed command
    subparsers.add_parser("seed", help="Seed initial corpus")

    # Search command
    search_parser = subparsers.add_parser("search", help="Test search")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--agent", default="discovery", help="Agent type")
    search_parser.add_argument("-k", type=int, default=3, help="Number of results")

    # Stats command
    subparsers.add_parser("stats", help="Show statistics")

    args = parser.parse_args()

    if args.command == "init":
        success = init_schema()
    elif args.command == "seed":
        success = seed_corpus()
    elif args.command == "search":
        success = test_search(args.query, args.agent, args.k)
    elif args.command == "stats":
        success = show_stats()
    else:
        parser.print_help()
        return

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
