"""
Code similarity detection using embeddings.

This module provides:
- Duplicate code detection
- Similar code clustering
- Code clone detection
- Refactoring opportunity identification
"""

import numpy as np
from typing import List, Dict, Optional, Any, Set, Tuple
from collections import defaultdict
from app.services.embeddings.embedder import CodeEmbedder


class SimilarityDetector:
    """
    Detect similar and duplicate code using embeddings.

    Useful for:
    - Finding code duplicates
    - Identifying refactoring opportunities
    - Detecting code clones
    - Finding related implementations
    """

    def __init__(self, embedder: Optional[CodeEmbedder] = None):
        """
        Initialize similarity detector.

        Args:
            embedder: CodeEmbedder instance
        """
        self.embedder = embedder or CodeEmbedder()

    def find_duplicates(
        self,
        code_elements: List[Dict[str, Any]],
        similarity_threshold: float = 0.95,
        language: str = "python",
    ) -> List[List[Dict[str, Any]]]:
        """
        Find duplicate or near-duplicate code.

        Args:
            code_elements: List of dicts with 'code' and 'metadata'
            similarity_threshold: Similarity threshold (0.95 = 95% similar)
            language: Programming language

        Returns:
            List of duplicate groups
        """
        if len(code_elements) < 2:
            return []

        # Generate embeddings
        codes = [elem["code"] for elem in code_elements]
        embeddings = self.embedder.embed_batch(codes, language=language)

        # Compute pairwise similarities
        similarity_matrix = np.dot(embeddings, embeddings.T)

        # Find duplicates
        duplicate_groups = []
        processed = set()

        for i in range(len(code_elements)):
            if i in processed:
                continue

            # Find all elements similar to i
            similar_indices = np.where(similarity_matrix[i] >= similarity_threshold)[0]

            if len(similar_indices) > 1:  # More than just itself
                group = []
                for idx in similar_indices:
                    if idx not in processed:
                        group.append({
                            **code_elements[idx],
                            "similarity_to_first": float(similarity_matrix[i, idx]),
                        })
                        processed.add(idx)

                if len(group) > 1:
                    duplicate_groups.append(group)

        return duplicate_groups

    def cluster_similar_code(
        self,
        code_elements: List[Dict[str, Any]],
        num_clusters: Optional[int] = None,
        similarity_threshold: float = 0.7,
        language: str = "python",
    ) -> List[List[Dict[str, Any]]]:
        """
        Cluster similar code elements.

        Args:
            code_elements: List of code dicts
            num_clusters: Optional number of clusters (auto-determined if None)
            similarity_threshold: Similarity threshold for clustering
            language: Programming language

        Returns:
            List of clusters (each cluster is a list of code elements)
        """
        if len(code_elements) < 2:
            return [code_elements] if code_elements else []

        # Generate embeddings
        codes = [elem["code"] for elem in code_elements]
        embeddings = self.embedder.embed_batch(codes, language=language)

        # Simple agglomerative clustering based on similarity
        clusters = [[i] for i in range(len(code_elements))]  # Start with each element in its own cluster

        # Compute similarity matrix
        similarity_matrix = np.dot(embeddings, embeddings.T)

        # Merge similar clusters
        while True:
            max_similarity = -1
            merge_pair = None

            # Find most similar pair of clusters
            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    # Compute cluster-to-cluster similarity (average)
                    similarities = []
                    for idx_i in clusters[i]:
                        for idx_j in clusters[j]:
                            similarities.append(similarity_matrix[idx_i, idx_j])

                    avg_similarity = np.mean(similarities)

                    if avg_similarity > max_similarity:
                        max_similarity = avg_similarity
                        merge_pair = (i, j)

            # Stop if no similar pairs found
            if max_similarity < similarity_threshold:
                break

            # Stop if reached desired number of clusters
            if num_clusters and len(clusters) <= num_clusters:
                break

            # Merge the most similar pair
            if merge_pair:
                i, j = merge_pair
                clusters[i].extend(clusters[j])
                clusters.pop(j)

        # Convert cluster indices to actual code elements
        result_clusters = []
        for cluster_indices in clusters:
            cluster = [code_elements[idx] for idx in cluster_indices]
            result_clusters.append(cluster)

        return result_clusters

    def find_code_clones(
        self,
        code_elements: List[Dict[str, Any]],
        language: str = "python",
    ) -> Dict[str, List[List[Dict[str, Any]]]]:
        """
        Detect different types of code clones.

        Clone types:
        - Type 1: Exact clones (>99% similar)
        - Type 2: Renamed clones (95-99% similar)
        - Type 3: Near-miss clones (85-95% similar)
        - Type 4: Semantic clones (70-85% similar)

        Args:
            code_elements: List of code dicts
            language: Programming language

        Returns:
            Dict mapping clone type to groups
        """
        clones = {
            "type1_exact": [],
            "type2_renamed": [],
            "type3_near_miss": [],
            "type4_semantic": [],
        }

        # Type 1: Exact clones (>99%)
        exact = self.find_duplicates(code_elements, 0.99, language)
        clones["type1_exact"] = exact

        # Type 2: Renamed clones (95-99%)
        renamed = self.find_duplicates(code_elements, 0.95, language)
        # Filter out exact clones
        renamed_filtered = [group for group in renamed if group not in exact]
        clones["type2_renamed"] = renamed_filtered

        # Type 3: Near-miss clones (85-95%)
        near_miss = self.find_duplicates(code_elements, 0.85, language)
        near_miss_filtered = [group for group in near_miss
                              if group not in exact and group not in renamed_filtered]
        clones["type3_near_miss"] = near_miss_filtered

        # Type 4: Semantic clones (70-85%)
        semantic = self.find_duplicates(code_elements, 0.70, language)
        semantic_filtered = [group for group in semantic
                            if group not in exact
                            and group not in renamed_filtered
                            and group not in near_miss_filtered]
        clones["type4_semantic"] = semantic_filtered

        return clones

    def suggest_refactorings(
        self,
        duplicate_groups: List[List[Dict[str, Any]]],
        min_group_size: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        Suggest refactoring opportunities based on duplicates.

        Args:
            duplicate_groups: Groups of duplicate code
            min_group_size: Minimum group size to suggest refactoring

        Returns:
            List of refactoring suggestions
        """
        suggestions = []

        for group in duplicate_groups:
            if len(group) < min_group_size:
                continue

            # Extract common metadata
            files = set()
            code_types = set()
            names = []

            for elem in group:
                metadata = elem.get("metadata", {})
                files.add(metadata.get("file", "unknown"))
                code_types.add(metadata.get("type", "unknown"))
                names.append(metadata.get("name", "unknown"))

            # Determine refactoring type
            if len(files) > 1:
                refactoring_type = "extract_function"  # Code duplicated across files
                description = f"Extract common logic from {len(group)} locations into a shared function"
            else:
                refactoring_type = "consolidate"  # Duplicates in same file
                description = f"Consolidate {len(group)} similar implementations in {list(files)[0]}"

            suggestions.append({
                "type": refactoring_type,
                "description": description,
                "duplicate_count": len(group),
                "locations": list(files),
                "names": names,
                "avg_similarity": np.mean([elem.get("similarity_to_first", 1.0) for elem in group]),
                "potential_savings": f"{len(group) - 1} duplicate(s)",
            })

        return suggestions

    def compare_implementations(
        self,
        impl1: str,
        impl2: str,
        language: str = "python",
    ) -> Dict[str, Any]:
        """
        Compare two implementations.

        Args:
            impl1: First implementation
            impl2: Second implementation
            language: Programming language

        Returns:
            Comparison result with similarity score and analysis
        """
        # Generate embeddings
        embeddings = self.embedder.embed_batch([impl1, impl2], language=language)

        # Compute similarity
        similarity = float(np.dot(embeddings[0], embeddings[1]))

        # Determine relationship
        if similarity > 0.99:
            relationship = "identical"
        elif similarity > 0.95:
            relationship = "near_identical"
        elif similarity > 0.85:
            relationship = "very_similar"
        elif similarity > 0.70:
            relationship = "similar"
        elif similarity > 0.50:
            relationship = "somewhat_similar"
        else:
            relationship = "different"

        return {
            "similarity": similarity,
            "relationship": relationship,
            "recommendation": self._get_comparison_recommendation(similarity),
        }

    def _get_comparison_recommendation(self, similarity: float) -> str:
        """Get recommendation based on similarity score"""
        if similarity > 0.95:
            return "Consider refactoring to eliminate duplication"
        elif similarity > 0.85:
            return "Review for potential consolidation"
        elif similarity > 0.70:
            return "These implementations share significant logic"
        elif similarity > 0.50:
            return "Some similarity detected - may be related functionality"
        else:
            return "Implementations appear to be different"

    def get_stats(self) -> Dict[str, Any]:
        """Get detector statistics"""
        return self.embedder.get_stats()
