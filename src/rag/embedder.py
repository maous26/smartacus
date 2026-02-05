"""
RAG Embedder
============

Generates embeddings using OpenAI text-embedding-3-small.
1536 dimensions, optimized for cost/latency.
"""

import logging
import os
from typing import List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Result of embedding generation."""
    embedding: List[float]
    token_count: int
    model: str


class RAGEmbedder:
    """
    Generates embeddings using OpenAI text-embedding-3-small.

    Cost: ~$0.00002 per 1K tokens (very cheap)
    Dimensions: 1536
    Max tokens: 8191
    """

    MODEL = "text-embedding-3-small"
    DIMENSIONS = 1536
    MAX_TOKENS = 8191

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("GPT_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required for embeddings")

        self._client = None
        self._total_tokens = 0
        self._total_requests = 0

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def embed(self, text: str) -> EmbeddingResult:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed (max 8191 tokens)

        Returns:
            EmbeddingResult with embedding vector
        """
        if not text.strip():
            raise ValueError("Cannot embed empty text")

        response = self.client.embeddings.create(
            model=self.MODEL,
            input=text,
            dimensions=self.DIMENSIONS,
        )

        embedding = response.data[0].embedding
        token_count = response.usage.total_tokens

        self._total_tokens += token_count
        self._total_requests += 1

        logger.debug(f"Embedded {token_count} tokens")

        return EmbeddingResult(
            embedding=embedding,
            token_count=token_count,
            model=self.MODEL,
        )

    def embed_batch(self, texts: List[str], batch_size: int = 100) -> List[EmbeddingResult]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            batch_size: Max texts per API call (default 100)

        Returns:
            List of EmbeddingResult
        """
        results = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            # Filter empty strings
            batch = [t for t in batch if t.strip()]
            if not batch:
                continue

            response = self.client.embeddings.create(
                model=self.MODEL,
                input=batch,
                dimensions=self.DIMENSIONS,
            )

            for j, data in enumerate(response.data):
                results.append(EmbeddingResult(
                    embedding=data.embedding,
                    token_count=response.usage.total_tokens // len(batch),  # Approx per text
                    model=self.MODEL,
                ))

            self._total_tokens += response.usage.total_tokens
            self._total_requests += 1

            logger.debug(f"Embedded batch of {len(batch)} texts ({response.usage.total_tokens} tokens)")

        return results

    def embed_query(self, query: str) -> List[float]:
        """
        Embed a search query.

        Same as embed() but returns just the vector for convenience.
        """
        result = self.embed(query)
        return result.embedding

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def total_requests(self) -> int:
        return self._total_requests

    @property
    def estimated_cost(self) -> float:
        """Estimated cost in USD."""
        # text-embedding-3-small: $0.00002 per 1K tokens
        return (self._total_tokens / 1000) * 0.00002
