"""
Demo mode API endpoints.

Provides endpoints for interacting with demo repositories:
- List available demo repositories
- Get demo repository details
- Check demo mode status
- Initialize/reload demo data (admin)
- Clear demo data (admin)
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from typing import List, Dict, Optional, Any
from pydantic import BaseModel
import logging

from app.demo import (
    DemoDataLoader,
    get_demo_config,
    is_demo_mode_enabled,
    is_demo_repo,
    list_demo_repos,
    get_demo_repo,
)
from app.services.embeddings import CodeEmbedder

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/demo",
    tags=["demo"],
)


# In-memory cache for demo graphs to avoid re-parsing on every request
_demo_graph_cache: Dict[str, Dict[str, Any]] = {}


# Response models
class DemoRepoSummary(BaseModel):
    """Demo repository summary"""
    id: str
    name: str
    description: str
    language: str
    file_count: int


class DemoRepoDetail(BaseModel):
    """Demo repository details"""
    id: str
    name: str
    description: str
    language: str
    files: Dict[str, str]
    file_count: int
    total_lines: int


class DemoStatusResponse(BaseModel):
    """Demo mode status"""
    enabled: bool
    data_loaded: bool
    max_demo_repos: int
    auto_load_on_startup: bool
    stats: Optional[Dict[str, Any]] = None


class DemoLoadResponse(BaseModel):
    """Demo data loading response"""
    status: str
    message: str
    stats: Optional[Dict[str, Any]] = None


# Dependency: Get data loader instance
# In production, this should be cached/singleton
_data_loader: Optional[DemoDataLoader] = None


def get_data_loader(
    embedder: Optional[CodeEmbedder] = None,
    neo4j_driver: Optional[Any] = None,
) -> DemoDataLoader:
    """
    Get demo data loader instance.

    In production, this should be properly dependency-injected.
    """
    global _data_loader

    if _data_loader is None:
        _data_loader = DemoDataLoader(
            embedder=embedder,
            neo4j_driver=neo4j_driver,
        )

    return _data_loader


# Endpoints


@router.get("/status", response_model=DemoStatusResponse)
async def get_demo_status():
    """
    Get demo mode status.

    Returns configuration and loading status.
    """
    config = get_demo_config()
    loader = get_data_loader()

    is_loaded = loader.is_demo_data_loaded()

    stats = None
    if is_loaded:
        stats = loader.get_stats()

    return DemoStatusResponse(
        enabled=config.enabled,
        data_loaded=is_loaded,
        max_demo_repos=config.max_demo_repos,
        auto_load_on_startup=config.auto_load_on_startup,
        stats=stats,
    )


@router.get("/repositories", response_model=List[DemoRepoSummary])
async def list_demo_repositories():
    """
    List available demo repositories.

    Returns:
        List of demo repository summaries
    """
    if not is_demo_mode_enabled():
        raise HTTPException(
            status_code=403,
            detail="Demo mode is not enabled",
        )

    repo_ids = list_demo_repos()

    summaries = []
    for repo_id in repo_ids:
        repo_data = get_demo_repo(repo_id)
        if repo_data:
            summaries.append(DemoRepoSummary(
                id=repo_data["id"],
                name=repo_data["name"],
                description=repo_data["description"],
                language=repo_data["language"],
                file_count=len(repo_data.get("files", {})),
            ))

    return summaries


@router.get("/repositories/{repo_id}", response_model=DemoRepoDetail)
async def get_demo_repository(repo_id: str):
    """
    Get demo repository details.

    Args:
        repo_id: Demo repository ID

    Returns:
        Demo repository details including file contents
    """
    if not is_demo_mode_enabled():
        raise HTTPException(
            status_code=403,
            detail="Demo mode is not enabled",
        )

    if not is_demo_repo(repo_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid demo repository ID: {repo_id}",
        )

    repo_data = get_demo_repo(repo_id)

    if not repo_data:
        raise HTTPException(
            status_code=404,
            detail=f"Demo repository not found: {repo_id}",
        )

    files = repo_data.get("files", {})

    # Calculate total lines
    total_lines = sum(
        len(content.split('\n'))
        for content in files.values()
    )

    return DemoRepoDetail(
        id=repo_data["id"],
        name=repo_data["name"],
        description=repo_data["description"],
        language=repo_data["language"],
        files=files,
        file_count=len(files),
        total_lines=total_lines,
    )


@router.get("/repositories/{repo_id}/graph")
async def get_demo_graph(repo_id: str):
    """
    Get graph data for a demo repository.

    Generates nodes and edges from parsed code:
    - File nodes
    - Function nodes
    - Class nodes
    - CONTAINS edges (file -> function/class)
    - IMPORTS edges (file -> file)

    Args:
        repo_id: Demo repository ID

    Returns:
        Graph with nodes and edges
    """
    if not is_demo_mode_enabled():
        raise HTTPException(
            status_code=403,
            detail="Demo mode is not enabled",
        )

    if not is_demo_repo(repo_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid demo repository ID: {repo_id}",
        )

    # Check cache first
    if repo_id in _demo_graph_cache:
        logger.debug(f"Returning cached graph for {repo_id}")
        return _demo_graph_cache[repo_id]

    repo_data = get_demo_repo(repo_id)
    if not repo_data:
        raise HTTPException(
            status_code=404,
            detail=f"Demo repository not found: {repo_id}",
        )

    logger.info(f"Generating graph for demo repository: {repo_id}")

    # Generate graph from repo data
    nodes = []
    edges = []
    node_id_counter = 0

    files = repo_data.get("files", {})

    for file_path, content in files.items():
        # Create file node
        file_node_id = f"{repo_id}-file-{node_id_counter}"
        node_id_counter += 1

        file_name = file_path.split("/")[-1]
        line_count = len(content.split("\n"))

        nodes.append({
            "id": file_node_id,
            "type": "file",
            "name": file_name,
            "path": file_path,
            "summary": f"Source file: {file_name}",
            "lineCount": line_count,
        })

        # Parse content to find functions and classes
        # Simple regex-based parsing for demo
        import re

        # Find Python functions
        if file_path.endswith(".py"):
            # Match function definitions
            func_pattern = r'^(?:async\s+)?def\s+(\w+)\s*\('
            for match in re.finditer(func_pattern, content, re.MULTILINE):
                func_name = match.group(1)
                func_node_id = f"{repo_id}-func-{node_id_counter}"
                node_id_counter += 1

                nodes.append({
                    "id": func_node_id,
                    "type": "function",
                    "name": func_name,
                    "path": file_path,
                    "summary": f"Function {func_name}",
                    "lineCount": 10,  # Approximate
                })

                # Add edge from file to function (defines relationship)
                edges.append({
                    "id": f"{repo_id}-edge-{len(edges)}",
                    "source": file_node_id,
                    "target": func_node_id,
                    "type": "defines",
                })

            # Match class definitions
            class_pattern = r'^class\s+(\w+)\s*[:\(]'
            for match in re.finditer(class_pattern, content, re.MULTILINE):
                class_name = match.group(1)
                class_node_id = f"{repo_id}-class-{node_id_counter}"
                node_id_counter += 1

                nodes.append({
                    "id": class_node_id,
                    "type": "class",
                    "name": class_name,
                    "path": file_path,
                    "summary": f"Class {class_name}",
                    "lineCount": 20,  # Approximate
                })

                edges.append({
                    "id": f"{repo_id}-edge-{len(edges)}",
                    "source": file_node_id,
                    "target": class_node_id,
                    "type": "defines",
                })

        # Find TypeScript/JavaScript functions and classes
        elif file_path.endswith((".ts", ".tsx", ".js", ".jsx")):
            # Match function declarations and arrow functions
            func_patterns = [
                r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(',
                r'(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>',
                r'(?:export\s+)?const\s+(\w+):\s*React\.FC',
            ]
            for pattern in func_patterns:
                for match in re.finditer(pattern, content):
                    func_name = match.group(1)
                    func_node_id = f"{repo_id}-func-{node_id_counter}"
                    node_id_counter += 1

                    nodes.append({
                        "id": func_node_id,
                        "type": "function",
                        "name": func_name,
                        "path": file_path,
                        "summary": f"Function/Component {func_name}",
                        "lineCount": 15,
                    })

                    edges.append({
                        "id": f"{repo_id}-edge-{len(edges)}",
                        "source": file_node_id,
                        "target": func_node_id,
                        "type": "defines",
                    })

            # Match class/interface definitions
            class_pattern = r'(?:export\s+)?(?:class|interface)\s+(\w+)'
            for match in re.finditer(class_pattern, content):
                class_name = match.group(1)
                class_node_id = f"{repo_id}-class-{node_id_counter}"
                node_id_counter += 1

                nodes.append({
                    "id": class_node_id,
                    "type": "class",
                    "name": class_name,
                    "path": file_path,
                    "summary": f"Class/Interface {class_name}",
                    "lineCount": 20,
                })

                edges.append({
                    "id": f"{repo_id}-edge-{len(edges)}",
                    "source": file_node_id,
                    "target": class_node_id,
                    "type": "defines",
                })

    # Cache the generated graph
    graph_result = {"nodes": nodes, "edges": edges}
    _demo_graph_cache[repo_id] = graph_result
    logger.info(f"Cached graph for {repo_id}: {len(nodes)} nodes, {len(edges)} edges")

    return graph_result


@router.post("/load", response_model=DemoLoadResponse)
async def load_demo_data(
    background_tasks: BackgroundTasks,
    force_reload: bool = False,
):
    """
    Load demo data into the system.

    This endpoint triggers demo data loading in the background.
    For production use, this should require admin authentication.

    Args:
        force_reload: Whether to clear and reload existing data

    Returns:
        Loading status and message
    """
    if not is_demo_mode_enabled():
        raise HTTPException(
            status_code=403,
            detail="Demo mode is not enabled",
        )

    loader = get_data_loader()

    # Check if already loaded
    if not force_reload and loader.is_demo_data_loaded():
        return DemoLoadResponse(
            status="already_loaded",
            message="Demo data is already loaded. Use force_reload=true to reload.",
            stats=loader.get_stats(),
        )

    # Load in background
    def load_task():
        try:
            logger.info("Starting demo data loading...")
            if force_reload and loader.is_demo_data_loaded():
                logger.info("Clearing existing demo data...")
                loader.clear_demo_data()
                # Clear graph cache
                _demo_graph_cache.clear()
                logger.info("Cleared demo graph cache")

            stats = loader.load_all_demo_repositories()
            logger.info(f"Demo data loaded: {stats}")
        except Exception as e:
            logger.error(f"Failed to load demo data: {e}", exc_info=True)

    background_tasks.add_task(load_task)

    return DemoLoadResponse(
        status="loading",
        message="Demo data loading started in background",
        stats=None,
    )


@router.post("/clear", response_model=DemoLoadResponse)
async def clear_demo_data(background_tasks: BackgroundTasks):
    """
    Clear demo data from the system.

    This endpoint removes all demo repositories and their data.
    For production use, this should require admin authentication.

    Returns:
        Clearing status and message
    """
    if not is_demo_mode_enabled():
        raise HTTPException(
            status_code=403,
            detail="Demo mode is not enabled",
        )

    loader = get_data_loader()

    # Check if loaded
    if not loader.is_demo_data_loaded():
        return DemoLoadResponse(
            status="not_loaded",
            message="No demo data to clear",
            stats=None,
        )

    # Clear in background
    def clear_task():
        try:
            logger.info("Clearing demo data...")
            stats = loader.clear_demo_data()
            # Clear graph cache
            _demo_graph_cache.clear()
            logger.info(f"Demo data cleared: {stats}")
        except Exception as e:
            logger.error(f"Failed to clear demo data: {e}", exc_info=True)

    background_tasks.add_task(clear_task)

    return DemoLoadResponse(
        status="clearing",
        message="Demo data clearing started in background",
        stats=None,
    )


@router.get("/search")
async def search_demo_code(
    query: str,
    repo_id: Optional[str] = None,
    top_k: int = 10,
):
    """
    Search demo code using natural language.

    Args:
        query: Natural language search query
        repo_id: Optional filter by demo repository
        top_k: Number of results to return

    Returns:
        Search results from demo repositories
    """
    if not is_demo_mode_enabled():
        raise HTTPException(
            status_code=403,
            detail="Demo mode is not enabled",
        )

    loader = get_data_loader()

    # Check if data is loaded
    if not loader.is_demo_data_loaded():
        raise HTTPException(
            status_code=404,
            detail="Demo data not loaded. Please load demo data first.",
        )

    # Validate repo filter
    if repo_id and not is_demo_repo(repo_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid demo repository ID: {repo_id}",
        )

    # Search using semantic search
    try:
        results = loader.semantic_search.search_by_query(
            query=query,
            top_k=top_k,
            repo_filter=repo_id,
        )

        return {
            "query": query,
            "repo_filter": repo_id,
            "results": results,
            "count": len(results),
        }

    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}",
        )


@router.get("/similar")
async def find_similar_code(
    code: str,
    language: str = "python",
    repo_id: Optional[str] = None,
    top_k: int = 5,
):
    """
    Find code similar to a given snippet.

    Args:
        code: Source code to search for
        language: Programming language
        repo_id: Optional filter by demo repository
        top_k: Number of results

    Returns:
        Similar code from demo repositories
    """
    if not is_demo_mode_enabled():
        raise HTTPException(
            status_code=403,
            detail="Demo mode is not enabled",
        )

    loader = get_data_loader()

    if not loader.is_demo_data_loaded():
        raise HTTPException(
            status_code=404,
            detail="Demo data not loaded. Please load demo data first.",
        )

    # Validate repo filter
    if repo_id and not is_demo_repo(repo_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid demo repository ID: {repo_id}",
        )

    # Search using code similarity
    try:
        results = loader.semantic_search.search_by_code(
            code=code,
            language=language,
            top_k=top_k,
        )

        # Filter by repo if specified
        if repo_id:
            results = [
                r for r in results
                if r.get("metadata", {}).get("repo_id") == repo_id
            ]

        return {
            "code_snippet": code[:200] + "..." if len(code) > 200 else code,
            "language": language,
            "repo_filter": repo_id,
            "results": results,
            "count": len(results),
        }

    except Exception as e:
        logger.error(f"Similarity search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Similarity search failed: {str(e)}",
        )
