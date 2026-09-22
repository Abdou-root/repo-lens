"""
Semantic code search using embeddings.

This module provides semantic search over code repositories:
- Natural language queries ("find authentication logic")
- Code-to-code search ("find functions similar to this one")
- Cross-language search
- Context-aware ranking
"""

import numpy as np
from typing import List, Dict, Optional, Any, Tuple
from app.services.embeddings.embedder import CodeEmbedder


class SemanticSearch:
    """
    Semantic code search using vector embeddings.

    Enables searching code using natural language queries or code snippets.
    """

    def __init__(
        self,
        embedder: Optional[CodeEmbedder] = None,
        neo4j_driver: Optional[Any] = None,
    ):
        """
        Initialize semantic search.

        Args:
            embedder: CodeEmbedder instance
            neo4j_driver: Neo4j driver for storing/retrieving embeddings
        """
        self.embedder = embedder or CodeEmbedder()
        self.neo4j_driver = neo4j_driver

        # In-memory index (use for prototyping, replace with vector DB in production)
        self._code_index: List[Dict[str, Any]] = []
        self._embeddings_matrix: Optional[np.ndarray] = None

    def index_code_element(
        self,
        code: str,
        metadata: Dict[str, Any],
        language: str = "python",
    ):
        """
        Add a code element to the search index.

        Args:
            code: Source code
            metadata: Metadata (type, name, file, etc.)
            language: Programming language
        """
        # Generate embedding
        embedding = self.embedder.embed_code(code, language)

        # Store in index
        self._code_index.append({
            "code": code,
            "embedding": embedding,
            "metadata": metadata,
            "language": language,
        })

        # Note: Call finalize_indexing() after batch operations to rebuild matrix

    def index_function(
        self,
        function_code: str,
        function_name: str,
        file_path: str,
        class_name: Optional[str] = None,
        docstring: Optional[str] = None,
        language: str = "python",
        repo_id: Optional[str] = None,
    ):
        """
        Index a function for search.

        Args:
            function_code: Function source code
            function_name: Name of the function
            file_path: File path
            class_name: Optional class name if method
            docstring: Optional docstring
            language: Programming language
            repo_id: Optional repository ID
        """
        embedding = self.embedder.embed_function(
            function_code,
            function_name,
            docstring,
            language
        )

        self._code_index.append({
            "code": function_code,
            "embedding": embedding,
            "metadata": {
                "type": "function",
                "name": function_name,
                "file": file_path,
                "class": class_name,
                "language": language,
                "repo_id": repo_id,
            },
            "language": language,
        })

        # Note: Call finalize_indexing() after batch operations to rebuild matrix

    def index_class(
        self,
        class_code: str,
        class_name: str,
        file_path: str,
        methods: Optional[List[str]] = None,
        docstring: Optional[str] = None,
        language: str = "python",
        repo_id: Optional[str] = None,
    ):
        """
        Index a class for search.

        Args:
            class_code: Class source code
            class_name: Name of the class
            file_path: File path
            methods: Optional list of method names
            docstring: Optional docstring
            language: Programming language
            repo_id: Optional repository ID
        """
        embedding = self.embedder.embed_class(
            class_code,
            class_name,
            methods,
            docstring,
            language
        )

        self._code_index.append({
            "code": class_code,
            "embedding": embedding,
            "metadata": {
                "type": "class",
                "name": class_name,
                "file": file_path,
                "methods": methods,
                "language": language,
                "repo_id": repo_id,
            },
            "language": language,
        })

        # Note: Call finalize_indexing() after batch operations to rebuild matrix

    def _rebuild_embeddings_matrix(self):
        """Rebuild the embeddings matrix for fast similarity search"""
        if self._code_index:
            self._embeddings_matrix = np.vstack([
                item["embedding"] for item in self._code_index
            ])

    def finalize_indexing(self):
        """
        Call after batch indexing operations to rebuild the embeddings matrix.

        This is a performance optimization - instead of rebuilding the matrix
        after each index_function/index_class call (O(n²) total), call this
        once after all items are indexed (O(n) total).
        """
        self._rebuild_embeddings_matrix()

    def search_by_query(
        self,
        query: str,
        top_k: int = 10,
        language_filter: Optional[str] = None,
        type_filter: Optional[str] = None,
        repo_filter: Optional[str] = None,
        similarity_threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        Search code using natural language query.

        Args:
            query: Natural language query
            top_k: Number of results to return
            language_filter: Filter by programming language
            type_filter: Filter by code type ('function', 'class', etc.)
            repo_filter: Filter by repository ID
            similarity_threshold: Minimum similarity score

        Returns:
            List of search results with code and metadata
        """
        if not self._code_index:
            return []

        # Generate query embedding
        query_embedding = self.embedder.embed_query(query)

        # Apply filters
        filtered_indices = []
        filtered_embeddings = []

        for i, item in enumerate(self._code_index):
            # Apply language filter
            if language_filter and item["language"] != language_filter:
                continue

            # Apply type filter
            if type_filter and item["metadata"].get("type") != type_filter:
                continue

            # Apply repo filter
            if repo_filter and item["metadata"].get("repo_id") != repo_filter:
                continue

            filtered_indices.append(i)
            filtered_embeddings.append(item["embedding"])

        if not filtered_embeddings:
            return []

        # Convert to matrix
        embeddings_matrix = np.vstack(filtered_embeddings)

        # Find most similar
        similar = self.embedder.find_most_similar(
            query_embedding,
            embeddings_matrix,
            top_k=top_k,
            threshold=similarity_threshold,
        )

        # Build results
        results = []
        for match in similar:
            original_idx = filtered_indices[match["index"]]
            item = self._code_index[original_idx]

            results.append({
                "code": item["code"],
                "metadata": item["metadata"],
                "similarity": match["similarity"],
                "language": item["language"],
            })

        return results

    def search_by_code(
        self,
        code: str,
        language: str = "python",
        top_k: int = 10,
        exclude_exact_match: bool = True,
        similarity_threshold: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Find code similar to a given code snippet.

        Args:
            code: Source code to search for
            language: Programming language
            top_k: Number of results
            exclude_exact_match: Whether to exclude the exact same code
            similarity_threshold: Minimum similarity

        Returns:
            List of similar code results
        """
        if not self._code_index:
            return []

        # Generate embedding for query code
        code_embedding = self.embedder.embed_code(code, language)

        # Find similar
        similar = self.embedder.find_most_similar(
            code_embedding,
            self._embeddings_matrix,
            top_k=top_k + 1 if exclude_exact_match else top_k,
            threshold=similarity_threshold,
        )

        # Build results
        results = []
        for match in similar:
            item = self._code_index[match["index"]]

            # Skip exact matches if requested
            if exclude_exact_match and match["similarity"] > 0.99:
                continue

            results.append({
                "code": item["code"],
                "metadata": item["metadata"],
                "similarity": match["similarity"],
                "language": item["language"],
            })

            if len(results) >= top_k:
                break

        return results

    def search_cross_language(
        self,
        query: str,
        source_language: str,
        target_languages: List[str],
        top_k: int = 5,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search for equivalent code across languages.

        Args:
            query: Natural language query or code description
            source_language: Source programming language
            target_languages: Target languages to search
            top_k: Results per language

        Returns:
            Dict mapping language to results
        """
        results_by_language = {}

        for lang in target_languages:
            results = self.search_by_query(
                query,
                top_k=top_k,
                language_filter=lang,
            )
            results_by_language[lang] = results

        return results_by_language

    def get_code_by_id(self, code_id: str, repo_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve specific code element by ID.

        Args:
            code_id: Code element ID
            repo_id: Repository ID

        Returns:
            Code element dict or None
        """
        # In real implementation, query Neo4j
        # For now, search in-memory index
        for item in self._code_index:
            metadata = item["metadata"]
            if (metadata.get("repo_id") == repo_id and
                metadata.get("name") == code_id):
                return item

        return None

    def get_stats(self) -> Dict[str, Any]:
        """Get search index statistics"""
        total_codes = len(self._code_index)

        # Count by type
        type_counts = {}
        lang_counts = {}

        for item in self._code_index:
            code_type = item["metadata"].get("type", "unknown")
            language = item["language"]

            type_counts[code_type] = type_counts.get(code_type, 0) + 1
            lang_counts[language] = lang_counts.get(language, 0) + 1

        return {
            "total_indexed": total_codes,
            "by_type": type_counts,
            "by_language": lang_counts,
            "embedder_stats": self.embedder.get_stats(),
        }

    def clear_index(self):
        """Clear the search index"""
        self._code_index.clear()
        self._embeddings_matrix = None
