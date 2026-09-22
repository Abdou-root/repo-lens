"""
Code embedding generation using sentence transformers.

This module generates embeddings for code snippets to enable:
- Semantic similarity search
- Code clustering
- Duplicate detection
- Related code finding
"""

import logging
import numpy as np
from typing import List, Dict, Optional, Any, Union
from functools import lru_cache
from sentence_transformers import SentenceTransformer
import hashlib
import os

logger = logging.getLogger(__name__)


class CodeEmbedder:
    """
    Generate embeddings for code using sentence transformers.

    Uses all-MiniLM-L6-v2 by default (fast, good quality, 384 dimensions).
    For code-specific tasks, can use microsoft/codebert-base or similar.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        cache_dir: Optional[str] = None,
        device: Optional[str] = None,
    ):
        """
        Initialize code embedder.

        Args:
            model_name: HuggingFace model name
                - "all-MiniLM-L6-v2": Fast, general purpose (384 dim)
                - "all-mpnet-base-v2": Higher quality (768 dim, slower)
                - "microsoft/codebert-base": Code-specific (768 dim)
            cache_dir: Directory to cache models
            device: Device to run on ('cpu', 'cuda', 'mps', etc.)
        """
        self.model_name = model_name

        # Load sentence transformer model
        logger.info(f"Loading embedding model: {model_name}...")
        self.model = SentenceTransformer(
            model_name,
            cache_folder=cache_dir,
            device=device,
        )
        logger.info(f"Model loaded. Embedding dimension: {self.model.get_sentence_embedding_dimension()}")

        # Track statistics
        self.embeddings_generated = 0
        self.cache_hits = 0

        # LRU cache with configurable size (default 10000 from env)
        cache_size = int(os.getenv("EMBEDDING_CACHE_SIZE", "10000"))
        self._embedding_cache = lru_cache(maxsize=cache_size)(self._compute_embedding_cached)

    def get_embedding_dimension(self) -> int:
        """Get embedding vector dimension"""
        return self.model.get_sentence_embedding_dimension()

    def _preprocess_code(
        self,
        code: str,
        language: str = "python",
        include_docstring: bool = True,
    ) -> str:
        """
        Preprocess code for embedding.

        Args:
            code: Source code
            language: Programming language
            include_docstring: Whether to include docstrings/comments

        Returns:
            Preprocessed code string
        """
        # Remove excessive whitespace
        lines = [line.rstrip() for line in code.split('\n')]

        # Remove empty lines at start/end
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()

        # Optionally remove comments/docstrings
        if not include_docstring and language == "python":
            # Simple comment removal (not perfect but good enough)
            filtered_lines = []
            in_docstring = False
            for line in lines:
                stripped = line.strip()

                # Toggle docstring state
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    if in_docstring:
                        in_docstring = False
                        continue
                    else:
                        in_docstring = True
                        continue

                # Skip if in docstring or comment
                if in_docstring or stripped.startswith('#'):
                    continue

                filtered_lines.append(line)

            lines = filtered_lines

        # Rejoin
        preprocessed = '\n'.join(lines)

        # Limit length (models have token limits)
        max_length = 500  # ~2000 tokens with 4 chars/token
        if len(preprocessed) > max_length:
            preprocessed = preprocessed[:max_length]

        return preprocessed

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text"""
        return hashlib.md5(text.encode()).hexdigest()

    def _compute_embedding_cached(self, text: str, normalize: bool) -> np.ndarray:
        """
        Internal method for cached embedding computation.
        LRU cache requires hashable arguments, so we cache by text+normalize.
        """
        embedding = self.model.encode(
            text,
            normalize_embeddings=normalize,
            show_progress_bar=False,
        )
        return embedding

    def embed_code(
        self,
        code: str,
        language: str = "python",
        normalize: bool = True,
        use_cache: bool = True,
    ) -> np.ndarray:
        """
        Generate embedding for a single code snippet.

        Args:
            code: Source code
            language: Programming language
            normalize: Whether to L2-normalize embedding
            use_cache: Whether to use cache

        Returns:
            Embedding vector as numpy array
        """
        # Preprocess
        preprocessed = self._preprocess_code(code, language)

        # Use LRU cached embedding computation if cache enabled
        if use_cache:
            # Check if result is cached by inspecting cache_info
            cache_info_before = self._embedding_cache.cache_info()
            embedding = self._embedding_cache(preprocessed, normalize)
            cache_info_after = self._embedding_cache.cache_info()

            # Track cache hits
            if cache_info_after.hits > cache_info_before.hits:
                self.cache_hits += 1
            else:
                self.embeddings_generated += 1
        else:
            # Bypass cache
            embedding = self.model.encode(
                preprocessed,
                normalize_embeddings=normalize,
                show_progress_bar=False,
            )
            self.embeddings_generated += 1

        return embedding

    def embed_batch(
        self,
        codes: List[str],
        language: str = "python",
        normalize: bool = True,
        batch_size: int = 32,
        show_progress: bool = False,
    ) -> np.ndarray:
        """
        Generate embeddings for multiple code snippets.

        Args:
            codes: List of source code strings
            language: Programming language
            normalize: Whether to L2-normalize embeddings
            batch_size: Batch size for encoding
            show_progress: Whether to show progress bar

        Returns:
            Array of embeddings (num_codes x embedding_dim)
        """
        # Preprocess all codes
        preprocessed = [
            self._preprocess_code(code, language)
            for code in codes
        ]

        # Generate embeddings in batches
        embeddings = self.model.encode(
            preprocessed,
            batch_size=batch_size,
            normalize_embeddings=normalize,
            show_progress_bar=show_progress,
        )

        self.embeddings_generated += len(codes)

        return embeddings

    def embed_function(
        self,
        function_code: str,
        function_name: str,
        docstring: Optional[str] = None,
        language: str = "python",
    ) -> np.ndarray:
        """
        Generate embedding for a function.

        Combines function name, docstring, and code for better semantic meaning.

        Args:
            function_code: Function source code
            function_name: Name of the function
            docstring: Optional docstring
            language: Programming language

        Returns:
            Embedding vector
        """
        # Combine components for semantic richness
        components = [f"Function: {function_name}"]

        if docstring:
            components.append(f"Description: {docstring}")

        components.append(f"Code:\n{function_code}")

        combined = "\n".join(components)

        return self.embed_code(combined, language)

    def embed_class(
        self,
        class_code: str,
        class_name: str,
        methods: Optional[List[str]] = None,
        docstring: Optional[str] = None,
        language: str = "python",
    ) -> np.ndarray:
        """
        Generate embedding for a class.

        Args:
            class_code: Class source code
            class_name: Name of the class
            methods: Optional list of method names
            docstring: Optional docstring
            language: Programming language

        Returns:
            Embedding vector
        """
        components = [f"Class: {class_name}"]

        if docstring:
            components.append(f"Description: {docstring}")

        if methods:
            components.append(f"Methods: {', '.join(methods[:10])}")  # First 10 methods

        components.append(f"Code:\n{class_code}")

        combined = "\n".join(components)

        return self.embed_code(combined, language)

    def embed_query(
        self,
        query: str,
        normalize: bool = True,
    ) -> np.ndarray:
        """
        Generate embedding for a search query.

        Args:
            query: Natural language query
            normalize: Whether to normalize embedding

        Returns:
            Query embedding vector
        """
        embedding = self.model.encode(
            query,
            normalize_embeddings=normalize,
            show_progress_bar=False,
        )

        return embedding

    def compute_similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray,
        metric: str = "cosine",
    ) -> float:
        """
        Compute similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            metric: Similarity metric ("cosine", "dot", "euclidean")

        Returns:
            Similarity score
        """
        if metric == "cosine":
            # Cosine similarity (assumes normalized embeddings)
            return float(np.dot(embedding1, embedding2))

        elif metric == "dot":
            # Dot product
            return float(np.dot(embedding1, embedding2))

        elif metric == "euclidean":
            # Euclidean distance (lower is more similar)
            return float(np.linalg.norm(embedding1 - embedding2))

        else:
            raise ValueError(f"Unknown metric: {metric}")

    def find_most_similar(
        self,
        query_embedding: np.ndarray,
        candidate_embeddings: np.ndarray,
        top_k: int = 5,
        threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find most similar embeddings to a query.

        Args:
            query_embedding: Query embedding vector
            candidate_embeddings: Array of candidate embeddings (N x dim)
            top_k: Number of results to return
            threshold: Optional similarity threshold

        Returns:
            List of dicts with 'index' and 'similarity' keys
        """
        # Compute similarities (assumes normalized embeddings)
        similarities = np.dot(candidate_embeddings, query_embedding)

        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]

        # Build results
        results = []
        for idx in top_indices:
            similarity = float(similarities[idx])

            # Apply threshold
            if threshold is not None and similarity < threshold:
                continue

            results.append({
                "index": int(idx),
                "similarity": similarity,
            })

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get embedder statistics"""
        cache_info = self._embedding_cache.cache_info()
        return {
            "model_name": self.model_name,
            "embedding_dimension": self.get_embedding_dimension(),
            "embeddings_generated": self.embeddings_generated,
            "cache_hits": self.cache_hits,
            "cache_size": cache_info.currsize,
            "cache_maxsize": cache_info.maxsize,
            "lru_cache_hits": cache_info.hits,
            "lru_cache_misses": cache_info.misses,
        }

    def clear_cache(self):
        """Clear embedding cache"""
        self._embedding_cache.cache_clear()
