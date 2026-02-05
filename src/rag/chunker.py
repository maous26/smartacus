"""
RAG Chunker
===========

Splits documents into chunks for embedding.

Rules:
- Chunk size: 400-800 tokens
- Overlap: 80-120 tokens
- Preserve headers in each chunk (anti-orphan)
- Stable chunking (same input = same chunks)
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple
from uuid import UUID

from .models import RAGDocument, RAGChunk

logger = logging.getLogger(__name__)


@dataclass
class ChunkConfig:
    """Chunking configuration."""
    min_tokens: int = 400
    max_tokens: int = 800
    overlap_tokens: int = 100
    # Approximate tokens per character (for estimation)
    chars_per_token: float = 4.0


class RAGChunker:
    """
    Splits documents into overlapping chunks.

    Preserves context by:
    1. Keeping headers in each chunk
    2. Overlapping tokens between chunks
    3. Respecting sentence boundaries when possible
    """

    def __init__(self, config: Optional[ChunkConfig] = None):
        self.config = config or ChunkConfig()

    def chunk_document(self, document: RAGDocument) -> List[RAGChunk]:
        """
        Split a document into chunks.

        Args:
            document: RAGDocument with content to chunk

        Returns:
            List of RAGChunk objects (without embeddings)
        """
        if not document.content.strip():
            logger.warning(f"Empty document: {document.title}")
            return []

        # Extract headers and content structure
        headers, sections = self._parse_structure(document.content)

        # Build context header (title + top-level headers)
        context_header = self._build_context_header(document.title, headers)

        # Split into chunks
        chunks = self._split_into_chunks(document.content, context_header)

        # Convert to RAGChunk objects
        result = []
        for i, (chunk_content, chunk_header) in enumerate(chunks):
            content_hash = self._hash_content(chunk_content)

            chunk = RAGChunk(
                document_id=document.id,
                chunk_index=i,
                content=chunk_content,
                content_hash=content_hash,
                context_header=chunk_header,
                doc_type=document.doc_type,
                domain=document.domain,
                marketplace=document.marketplace,
                category=document.category,
                language=document.language,
                token_count=self._estimate_tokens(chunk_content),
                metadata=document.metadata.copy(),
            )
            result.append(chunk)

        logger.info(f"Chunked '{document.title}' into {len(result)} chunks")
        return result

    def _parse_structure(self, content: str) -> Tuple[List[str], List[str]]:
        """
        Parse document structure to extract headers.

        Returns:
            Tuple of (headers list, sections list)
        """
        headers = []
        sections = []

        # Match markdown-style headers
        header_pattern = re.compile(r'^(#{1,3})\s+(.+)$', re.MULTILINE)

        for match in header_pattern.finditer(content):
            level = len(match.group(1))
            text = match.group(2).strip()
            headers.append(f"{'#' * level} {text}")

        # Split by headers
        sections = header_pattern.split(content)

        return headers, sections

    def _build_context_header(self, title: str, headers: List[str]) -> str:
        """
        Build context header to prepend to each chunk.
        """
        context_parts = [f"Document: {title}"]

        # Add first 2-3 top-level headers for context
        top_headers = [h for h in headers if h.startswith('# ') or h.startswith('## ')][:3]
        if top_headers:
            context_parts.append("Sections: " + " > ".join(h.lstrip('#').strip() for h in top_headers))

        return " | ".join(context_parts)

    def _split_into_chunks(
        self,
        content: str,
        context_header: str
    ) -> List[Tuple[str, str]]:
        """
        Split content into overlapping chunks.

        Returns:
            List of (chunk_content, chunk_context_header) tuples
        """
        # Convert to approximate character limits
        min_chars = int(self.config.min_tokens * self.config.chars_per_token)
        max_chars = int(self.config.max_tokens * self.config.chars_per_token)
        overlap_chars = int(self.config.overlap_tokens * self.config.chars_per_token)

        chunks = []
        text = content.strip()

        if len(text) <= max_chars:
            # Single chunk
            return [(text, context_header)]

        # Split into sentences for cleaner boundaries
        sentences = self._split_sentences(text)

        current_chunk = []
        current_length = 0
        current_header = context_header

        for sentence in sentences:
            sentence_len = len(sentence)

            if current_length + sentence_len > max_chars and current_length >= min_chars:
                # Save current chunk
                chunk_text = ' '.join(current_chunk)
                chunks.append((chunk_text, current_header))

                # Start new chunk with overlap
                overlap_text = self._get_overlap(current_chunk, overlap_chars)
                current_chunk = [overlap_text] if overlap_text else []
                current_length = len(overlap_text) if overlap_text else 0

                # Update context header with nearby headers
                current_header = self._update_context_header(context_header, chunk_text)

            current_chunk.append(sentence)
            current_length += sentence_len

        # Don't forget the last chunk
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            if chunk_text.strip():
                chunks.append((chunk_text, current_header))

        return chunks

    def _split_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences.
        """
        # Simple sentence splitting (can be improved with NLTK/spaCy)
        sentence_pattern = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')
        sentences = sentence_pattern.split(text)

        # Further split very long sentences
        result = []
        for sentence in sentences:
            if len(sentence) > self.config.max_tokens * self.config.chars_per_token:
                # Split on commas or semicolons
                parts = re.split(r'[,;]\s+', sentence)
                result.extend(parts)
            else:
                result.append(sentence)

        return [s.strip() for s in result if s.strip()]

    def _get_overlap(self, sentences: List[str], overlap_chars: int) -> str:
        """
        Get overlap text from end of previous chunk.
        """
        overlap_parts = []
        total_len = 0

        for sentence in reversed(sentences):
            if total_len + len(sentence) > overlap_chars:
                break
            overlap_parts.insert(0, sentence)
            total_len += len(sentence)

        return ' '.join(overlap_parts)

    def _update_context_header(self, base_header: str, chunk_text: str) -> str:
        """
        Update context header based on headers found in chunk.
        """
        # Find any headers in the chunk
        header_match = re.search(r'^(#{1,3})\s+(.+)$', chunk_text, re.MULTILINE)
        if header_match:
            section = header_match.group(2).strip()
            return f"{base_header} | Current: {section}"
        return base_header

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        """
        return int(len(text) / self.config.chars_per_token)

    def _hash_content(self, content: str) -> str:
        """
        Generate SHA256 hash of content for deduplication.
        """
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
