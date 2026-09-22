"""
Semantic search API endpoints.

Provides endpoints for:
- Semantic code search
- Code similarity detection
- Duplicate finding
- Cross-repository search
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
import logging

from app.services.embeddings import (
    CodeEmbedder,
    SimilarityDetector,
)
from app.db.vector_store import (
    count_indexed,
    fetch_code_elements,
    vector_search,
)
from app.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/search",
    tags=["search"],
)


# Request/Response models
class SemanticSearchRequest(BaseModel):
    """Semantic search request"""
    query: str = Field(..., description="Natural language search query")
    repo_id: Optional[str] = Field(None, description="Filter by repository")
    language: Optional[str] = Field(None, description="Filter by language")
    code_type: Optional[str] = Field(None, description="Filter by type (function, class, etc.)")
    top_k: int = Field(10, ge=1, le=50, description="Number of results to return")
    similarity_threshold: float = Field(0.3, ge=0.0, le=1.0, description="Minimum similarity score")


class CodeSearchRequest(BaseModel):
    """Code-to-code search request"""
    code: str = Field(..., description="Code snippet to search for")
    language: str = Field(default="python", description="Programming language")
    repo_id: Optional[str] = Field(None, description="Filter by repository")
    top_k: int = Field(10, ge=1, le=50, description="Number of results")
    exclude_exact: bool = Field(True, description="Exclude exact matches")


class SearchResult(BaseModel):
    """Single search result"""
    node_id: Optional[str] = None
    code: str
    metadata: Dict[str, Any]
    similarity: float
    language: str


class SearchResponse(BaseModel):
    """Search response with results"""
    query: str
    results: List[SearchResult]
    count: int
    total_indexed: int


class DuplicateRequest(BaseModel):
    """Request to find duplicates"""
    repo_id: str = Field(..., description="Repository ID to analyze")
    similarity_threshold: float = Field(0.95, ge=0.7, le=1.0)
    language: Optional[str] = None


class DuplicateGroup(BaseModel):
    """Group of duplicate code"""
    items: List[Dict[str, Any]]
    similarity: float
    count: int


class DuplicateResponse(BaseModel):
    """Duplicate detection response"""
    repo_id: str
    duplicate_groups: List[DuplicateGroup]
    total_duplicates: int
    refactoring_suggestions: List[Dict[str, Any]]


class SimilarityRequest(BaseModel):
    """Request to compare two code snippets"""
    code1: str
    code2: str
    language: str = "python"


class SimilarityResponse(BaseModel):
    """Code similarity comparison"""
    similarity: float
    relationship: str
    recommendation: str


# Dependencies - Thread-safe singleton caches

import threading

_cache_lock = threading.Lock()
_embedder_cache = None
_detector_cache = None


def get_embedder():
    """Get or create embedder instance (thread-safe)"""
    global _embedder_cache
    if _embedder_cache is None:
        with _cache_lock:
            # Double-check after acquiring lock
            if _embedder_cache is None:
                _embedder_cache = CodeEmbedder(model_name="all-MiniLM-L6-v2")
    return _embedder_cache


def get_similarity_detector(embedder: CodeEmbedder = Depends(get_embedder)):
    """Get or create similarity detector (thread-safe)"""
    global _detector_cache
    if _detector_cache is None:
        with _cache_lock:
            if _detector_cache is None:
                _detector_cache = SimilarityDetector(embedder=embedder)
    return _detector_cache


# Endpoints

@router.post("/semantic", response_model=SearchResponse)
async def semantic_search(
    request: SemanticSearchRequest,
    embedder: CodeEmbedder = Depends(get_embedder),
    current_user: dict = Depends(get_current_user),
):
    """
    Search code using natural language.

    Use natural language queries like "find authentication logic"
    to search through indexed code. The query is embedded with the same
    model the worker used, and Neo4j's vector index finds the nearest nodes.
    """
    try:
        query_vector = embedder.embed_query(request.query)

        rows = vector_search(
            query_vector=[float(x) for x in query_vector],
            repo_id=request.repo_id,
            top_k=request.top_k,
            similarity_threshold=request.similarity_threshold,
            language=request.language,
            code_type=request.code_type,
        )

        results = [
            SearchResult(
                node_id=row.get("node_id"),
                code=row.get("code") or "",
                similarity=float(row.get("similarity", 0.0)),
                language=row.get("language") or "unknown",
                metadata={
                    # Kept for backwards compatibility with older clients
                    "node_id": row.get("node_id"),
                    "name": row.get("name"),
                    "type": row.get("type"),
                    "file": row.get("path"),
                    "path": row.get("path"),
                    "summary": row.get("summary"),
                    "repo_id": request.repo_id,
                },
            )
            for row in rows
        ]

        return SearchResponse(
            query=request.query,
            results=results,
            count=len(results),
            total_indexed=count_indexed(request.repo_id),
        )

    except Exception as e:
        logger.error(f"Semantic search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}",
        )


@router.post("/code", response_model=SearchResponse)
async def code_search(
    request: CodeSearchRequest,
    embedder: CodeEmbedder = Depends(get_embedder),
    current_user: dict = Depends(get_current_user),
):
    """
    Find similar code snippets.

    Search for code similar to a given snippet using embeddings.
    """
    try:
        query_vector = embedder.embed_code(request.code, language=request.language)

        rows = vector_search(
            query_vector=[float(x) for x in query_vector],
            repo_id=request.repo_id,
            top_k=request.top_k,
            language=request.language,
        )

        if request.exclude_exact:
            needle = request.code.strip()
            rows = [r for r in rows if (r.get("code") or "").strip() != needle]

        results = [
            SearchResult(
                node_id=row.get("node_id"),
                code=row.get("code") or "",
                similarity=float(row.get("similarity", 0.0)),
                language=row.get("language") or "unknown",
                metadata={
                    "node_id": row.get("node_id"),
                    "name": row.get("name"),
                    "type": row.get("type"),
                    "file": row.get("path"),
                    "path": row.get("path"),
                    "repo_id": request.repo_id,
                },
            )
            for row in rows
        ]

        return SearchResponse(
            query=f"Code snippet ({request.language})",
            results=results,
            count=len(results),
            total_indexed=count_indexed(request.repo_id),
        )

    except Exception as e:
        logger.error(f"Code search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Code search failed: {str(e)}",
        )


@router.post("/compare", response_model=SimilarityResponse)
async def compare_code(
    request: SimilarityRequest,
    detector: SimilarityDetector = Depends(get_similarity_detector),
    current_user: dict = Depends(get_current_user),
):
    """
    Compare two code snippets for similarity.

    Returns similarity score and relationship analysis.
    """
    try:
        result = detector.compare_implementations(
            impl1=request.code1,
            impl2=request.code2,
            language=request.language,
        )

        return SimilarityResponse(**result)

    except Exception as e:
        logger.error(f"Code comparison failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Comparison failed: {str(e)}",
        )


@router.post("/duplicates", response_model=DuplicateResponse)
async def find_duplicates(
    request: DuplicateRequest,
    detector: SimilarityDetector = Depends(get_similarity_detector),
    current_user: dict = Depends(get_current_user),
):
    """
    Find duplicate or near-duplicate code in a repository.

    Analyzes a repository to identify code duplication and
    provide refactoring suggestions.
    """
    try:
        # Read the repository's code elements from Neo4j (shared across
        # processes) rather than from a per-process in-memory index.
        rows = fetch_code_elements(request.repo_id, language=request.language)

        code_elements = [
            {
                "code": row["code"],
                "metadata": {
                    "node_id": row.get("node_id"),
                    "name": row.get("name"),
                    "type": row.get("type"),
                    "file": row.get("path"),
                    "repo_id": request.repo_id,
                },
            }
            for row in rows
        ]

        if not code_elements:
            return DuplicateResponse(
                repo_id=request.repo_id,
                duplicate_groups=[],
                total_duplicates=0,
                refactoring_suggestions=[],
            )

        # Find duplicates
        duplicates = detector.find_duplicates(
            code_elements=code_elements,
            similarity_threshold=request.similarity_threshold,
            language=request.language or "python",
        )

        # Format duplicate groups
        duplicate_groups = []
        for group in duplicates:
            duplicate_groups.append(DuplicateGroup(
                items=[
                    {
                        "name": item["metadata"].get("name", "unknown"),
                        "file": item["metadata"].get("file", "unknown"),
                        "similarity": item.get("similarity_to_first", 1.0),
                    }
                    for item in group
                ],
                similarity=group[0].get("similarity_to_first", 1.0) if group else 0,
                count=len(group),
            ))

        # Get refactoring suggestions
        suggestions = detector.suggest_refactorings(duplicates)

        return DuplicateResponse(
            repo_id=request.repo_id,
            duplicate_groups=duplicate_groups,
            total_duplicates=sum(len(g.items) for g in duplicate_groups),
            refactoring_suggestions=suggestions,
        )

    except Exception as e:
        logger.error(f"Duplicate detection failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Duplicate detection failed: {str(e)}",
        )


@router.get("/stats")
async def get_search_stats(
    repo_id: Optional[str] = Query(None, description="Filter by repository"),
    embedder: CodeEmbedder = Depends(get_embedder),
    current_user: dict = Depends(get_current_user),
):
    """
    Get search index statistics.

    Returns information about indexed code elements.
    """
    try:
        return {
            "total_indexed": count_indexed(repo_id),
            "embedder_stats": embedder.get_stats(),
        }

    except Exception as e:
        logger.error(f"Failed to get stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get statistics: {str(e)}",
        )


@router.get("/health")
async def search_health_check():
    """
    Health check for search service.

    Returns service status and readiness.
    """
    try:
        embedder = get_embedder()
        embedder_stats = embedder.get_stats()
        total_indexed = count_indexed()

        return {
            "status": "healthy",
            "embedder": {
                "model": embedder_stats["model_name"],
                "dimension": embedder_stats["embedding_dimension"],
            },
            "index": {
                "total_indexed": total_indexed,
                "ready": total_indexed > 0,
            },
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return {
            "status": "unhealthy",
            "error": str(e),
        }
