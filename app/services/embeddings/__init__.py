"""
Embedding services for semantic code search and similarity detection.

This package provides:
- Code embedding generation using sentence transformers
- Vector similarity search
- Semantic code search
- Duplicate/similar code detection
"""

from app.services.embeddings.embedder import CodeEmbedder
from app.services.embeddings.search import SemanticSearch
from app.services.embeddings.similarity import SimilarityDetector

__all__ = [
    'CodeEmbedder',
    'SemanticSearch',
    'SimilarityDetector',
]
