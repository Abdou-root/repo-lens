"""
Demo data loader.

This module loads demo repositories into the system:
- Parses demo code using tree-sitter
- Generates embeddings for code elements
- Stores in Neo4j graph database
- Provides initialization and cleanup functions
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from app.demo.repositories import (
    DEMO_REPOSITORIES,
    get_demo_repo,
    list_demo_repos,
)
from app.demo.config import DemoConfig, get_demo_config, is_demo_repo
from app.services.parser import PythonParser, TypeScriptParser
from app.services.embeddings import CodeEmbedder, SemanticSearch
from app.services.parsers.base import FunctionDef, ClassDef

logger = logging.getLogger(__name__)


class DemoDataLoader:
    """
    Load demo repositories into the system.

    Handles parsing, embedding generation, and Neo4j storage.
    """

    def __init__(
        self,
        embedder: Optional[CodeEmbedder] = None,
        neo4j_driver: Optional[Any] = None,
        config: Optional[DemoConfig] = None,
    ):
        """
        Initialize demo data loader.

        Args:
            embedder: CodeEmbedder instance
            neo4j_driver: Neo4j driver instance
            config: Demo configuration
        """
        self.embedder = embedder or CodeEmbedder()
        self.neo4j_driver = neo4j_driver
        self.config = config or get_demo_config()

        # Initialize parsers
        self.python_parser = PythonParser()
        self.ts_parser = TypeScriptParser()

        # Initialize semantic search (uses embedder)
        self.semantic_search = SemanticSearch(
            embedder=self.embedder,
            neo4j_driver=neo4j_driver,
        )

        # Track loading statistics
        self.stats = {
            "repos_loaded": 0,
            "files_parsed": 0,
            "functions_indexed": 0,
            "classes_indexed": 0,
            "embeddings_generated": 0,
            "errors": [],
        }

    def load_all_demo_repositories(self) -> Dict[str, Any]:
        """
        Load all demo repositories.

        Returns:
            Loading statistics
        """
        logger.info("Loading all demo repositories...")

        if not self.config.enabled:
            logger.warning("Demo mode is disabled")
            return {"status": "disabled"}

        # Reset stats
        self.stats = {
            "repos_loaded": 0,
            "files_parsed": 0,
            "functions_indexed": 0,
            "classes_indexed": 0,
            "embeddings_generated": 0,
            "errors": [],
        }

        # Load each demo repository
        demo_repos = list_demo_repos()

        for repo_id in demo_repos[:self.config.max_demo_repos]:
            try:
                logger.info(f"Loading demo repository: {repo_id}")
                self.load_demo_repository(repo_id)
                self.stats["repos_loaded"] += 1
            except Exception as e:
                logger.error(f"Failed to load {repo_id}: {e}")
                self.stats["errors"].append({
                    "repo_id": repo_id,
                    "error": str(e),
                })

        # CRITICAL: Rebuild embeddings matrix ONCE after all indexing is done
        # This is O(n) vs O(n²) if rebuilt after each item
        self.semantic_search.finalize_indexing()

        # Get embedder stats
        embedder_stats = self.embedder.get_stats()
        self.stats["embeddings_generated"] = embedder_stats["embeddings_generated"]

        logger.info(f"Demo data loading complete: {self.stats}")

        return self.stats

    def load_demo_repository(self, repo_id: str) -> Dict[str, Any]:
        """
        Load a specific demo repository.

        Args:
            repo_id: Demo repository ID

        Returns:
            Loading statistics for this repo
        """
        # Get demo repository data
        repo_data = get_demo_repo(repo_id)

        if not repo_data:
            raise ValueError(f"Demo repository not found: {repo_id}")

        # Note: Removed redundant log - repo_id already logged in load_all_demo_repositories()

        # Create repository in Neo4j if driver available
        if self.neo4j_driver:
            self._create_repository_node(repo_data)

        # Process each file
        files_data = repo_data.get("files", {})

        for file_path, file_content in files_data.items():
            try:
                self._process_demo_file(
                    repo_id=repo_id,
                    file_path=file_path,
                    file_content=file_content,
                    repo_data=repo_data,
                )
                self.stats["files_parsed"] += 1
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {e}")
                self.stats["errors"].append({
                    "file": file_path,
                    "error": str(e),
                })

        return {
            "repo_id": repo_id,
            "files_processed": len(files_data),
        }

    def _process_demo_file(
        self,
        repo_id: str,
        file_path: str,
        file_content: str,
        repo_data: Dict[str, Any],
    ):
        """
        Process a demo file: parse and index.

        Args:
            repo_id: Repository ID
            file_path: File path
            file_content: File content
            repo_data: Repository metadata
        """
        logger.debug(f"Processing file: {file_path}")

        # Determine language
        language = self._detect_language(file_path)

        if language not in ["python", "typescript", "javascript"]:
            logger.warning(f"Unsupported language for {file_path}")
            return

        # Create temporary file for parsing (parsers expect file paths)
        import tempfile
        import os

        try:
            # Determine file suffix
            suffix = ".py" if language == "python" else ".ts"

            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix=suffix,
                delete=False,
                encoding='utf-8'
            ) as tmp:
                tmp.write(file_content)
                tmp_path = tmp.name

            # Parse file
            if language == "python":
                parsed_data = self.python_parser.parse_file(tmp_path)
            else:  # TypeScript/JavaScript
                parsed_data = self.ts_parser.parse_file(tmp_path)

            # Clean up temp file
            os.unlink(tmp_path)

        except Exception as e:
            logger.error(f"Failed to parse {file_path}: {e}")
            raise

        # Create file node in Neo4j
        if self.neo4j_driver:
            self._create_file_node(
                repo_id=repo_id,
                file_path=file_path,
                language=language,
                parsed_data=parsed_data,
            )

        # Index functions
        for func in parsed_data.functions:
            self._index_function(
                repo_id=repo_id,
                file_path=file_path,
                function_data=func,
                language=language,
            )
            self.stats["functions_indexed"] += 1

        # Index classes
        for cls in parsed_data.classes:
            self._index_class(
                repo_id=repo_id,
                file_path=file_path,
                class_data=cls,
                language=language,
            )
            self.stats["classes_indexed"] += 1

    def _index_function(
        self,
        repo_id: str,
        file_path: str,
        function_data: FunctionDef,
        language: str,
    ):
        """
        Index a function for semantic search.

        Args:
            repo_id: Repository ID
            file_path: File path
            function_data: Function definition dataclass
            language: Programming language
        """
        function_name = function_data.name
        function_code = function_data.code
        docstring = function_data.docstring

        # Index in semantic search
        self.semantic_search.index_function(
            function_code=function_code,
            function_name=function_name,
            file_path=file_path,
            docstring=docstring,
            language=language,
            repo_id=repo_id,
        )

        # Create function node in Neo4j
        if self.neo4j_driver:
            self._create_function_node(
                repo_id=repo_id,
                file_path=file_path,
                function_data=function_data,
                language=language,
            )

        logger.debug(f"Indexed function: {function_name} in {file_path}")

    def _index_class(
        self,
        repo_id: str,
        file_path: str,
        class_data: ClassDef,
        language: str,
    ):
        """
        Index a class for semantic search.

        Args:
            repo_id: Repository ID
            file_path: File path
            class_data: Class definition dataclass
            language: Programming language
        """
        class_name = class_data.name
        class_code = class_data.code
        docstring = class_data.docstring
        methods = class_data.methods

        # Index in semantic search
        self.semantic_search.index_class(
            class_code=class_code,
            class_name=class_name,
            file_path=file_path,
            methods=methods,
            docstring=docstring,
            language=language,
            repo_id=repo_id,
        )

        # Create class node in Neo4j
        if self.neo4j_driver:
            self._create_class_node(
                repo_id=repo_id,
                file_path=file_path,
                class_data=class_data,
                language=language,
            )

        logger.debug(f"Indexed class: {class_name} in {file_path}")

    def _create_repository_node(self, repo_data: Dict[str, Any]):
        """Create repository node in Neo4j"""
        with self.neo4j_driver.session() as session:
            session.run(
                """
                MERGE (r:Repository {id: $repo_id})
                SET r.name = $name,
                    r.description = $description,
                    r.language = $language,
                    r.is_demo = true,
                    r.created_at = datetime($created_at)
                """,
                repo_id=repo_data["id"],
                name=repo_data["name"],
                description=repo_data["description"],
                language=repo_data["language"],
                created_at=datetime.utcnow().isoformat(),
            )

        logger.debug(f"Created repository node: {repo_data['id']}")

    def _create_file_node(
        self,
        repo_id: str,
        file_path: str,
        language: str,
        parsed_data: Any,  # ParseResult
    ):
        """Create file node in Neo4j"""
        with self.neo4j_driver.session() as session:
            session.run(
                """
                MATCH (r:Repository {id: $repo_id})
                MERGE (f:File {path: $file_path, repo_id: $repo_id})
                SET f.language = $language,
                    f.lines_of_code = $loc,
                    f.is_demo = true
                MERGE (r)-[:CONTAINS]->(f)
                """,
                repo_id=repo_id,
                file_path=file_path,
                language=language,
                loc=parsed_data.line_count,
            )

        logger.debug(f"Created file node: {file_path}")

    def _create_function_node(
        self,
        repo_id: str,
        file_path: str,
        function_data: FunctionDef,
        language: str,
    ):
        """Create function node in Neo4j"""
        with self.neo4j_driver.session() as session:
            session.run(
                """
                MATCH (f:File {path: $file_path, repo_id: $repo_id})
                MERGE (fn:Function {
                    name: $name,
                    file_path: $file_path,
                    repo_id: $repo_id
                })
                SET fn.code = $code,
                    fn.docstring = $docstring,
                    fn.language = $language,
                    fn.start_line = $start_line,
                    fn.line_count = $line_count,
                    fn.is_demo = true
                MERGE (f)-[:DEFINES]->(fn)
                """,
                repo_id=repo_id,
                file_path=file_path,
                name=function_data.name,
                code=function_data.code,
                docstring=function_data.docstring,
                language=language,
                start_line=function_data.line_number,
                line_count=function_data.line_count,
            )

        logger.debug(f"Created function node: {function_data.name}")

    def _create_class_node(
        self,
        repo_id: str,
        file_path: str,
        class_data: ClassDef,
        language: str,
    ):
        """Create class node in Neo4j"""
        with self.neo4j_driver.session() as session:
            session.run(
                """
                MATCH (f:File {path: $file_path, repo_id: $repo_id})
                MERGE (c:Class {
                    name: $name,
                    file_path: $file_path,
                    repo_id: $repo_id
                })
                SET c.code = $code,
                    c.docstring = $docstring,
                    c.language = $language,
                    c.start_line = $start_line,
                    c.line_count = $line_count,
                    c.is_demo = true
                MERGE (f)-[:DEFINES]->(c)
                """,
                repo_id=repo_id,
                file_path=file_path,
                name=class_data.name,
                code=class_data.code,
                docstring=class_data.docstring,
                language=language,
                start_line=class_data.line_number,
                line_count=class_data.line_count,
            )

        logger.debug(f"Created class node: {class_data.name}")

    def _detect_language(self, file_path: str) -> str:
        """
        Detect programming language from file extension.

        Args:
            file_path: File path

        Returns:
            Language name
        """
        if file_path.endswith(".py"):
            return "python"
        elif file_path.endswith(".ts") or file_path.endswith(".tsx"):
            return "typescript"
        elif file_path.endswith(".js") or file_path.endswith(".jsx"):
            return "javascript"
        else:
            return "unknown"

    def is_demo_data_loaded(self) -> bool:
        """
        Check if demo data is already loaded.

        Returns:
            True if demo data exists
        """
        if not self.neo4j_driver:
            # Check in-memory search index
            stats = self.semantic_search.get_stats()
            return stats["total_indexed"] > 0

        # Check Neo4j
        with self.neo4j_driver.session() as session:
            result = session.run(
                """
                MATCH (r:Repository {is_demo: true})
                RETURN count(r) as count
                """
            )
            record = result.single()
            return record["count"] > 0 if record else False

    def clear_demo_data(self) -> Dict[str, Any]:
        """
        Remove all demo data.

        Returns:
            Deletion statistics
        """
        logger.info("Clearing demo data...")

        stats = {
            "repos_deleted": 0,
            "files_deleted": 0,
            "functions_deleted": 0,
            "classes_deleted": 0,
        }

        # Clear semantic search index
        # Only clear demo repo items
        if hasattr(self.semantic_search, '_code_index'):
            original_count = len(self.semantic_search._code_index)
            self.semantic_search._code_index = [
                item for item in self.semantic_search._code_index
                if not is_demo_repo(item.get("metadata", {}).get("repo_id", ""))
            ]
            cleared = original_count - len(self.semantic_search._code_index)
            logger.info(f"Cleared {cleared} items from semantic search index")
            self.semantic_search._rebuild_embeddings_matrix()

        # Clear Neo4j if available
        if self.neo4j_driver:
            with self.neo4j_driver.session() as session:
                # Delete all demo nodes and relationships
                result = session.run(
                    """
                    MATCH (r:Repository {is_demo: true})
                    OPTIONAL MATCH (r)-[*]-(n)
                    WHERE n.is_demo = true
                    WITH r, collect(DISTINCT n) as nodes
                    DETACH DELETE r
                    WITH nodes
                    UNWIND nodes as node
                    DETACH DELETE node
                    RETURN count(DISTINCT node) as deleted_count
                    """
                )
                record = result.single()
                if record:
                    stats["nodes_deleted"] = record["deleted_count"]

        logger.info(f"Demo data cleared: {stats}")

        return stats

    def get_stats(self) -> Dict[str, Any]:
        """
        Get data loader statistics.

        Returns:
            Statistics dict
        """
        return {
            **self.stats,
            "demo_config": {
                "enabled": self.config.enabled,
                "max_repos": self.config.max_demo_repos,
            },
            "search_stats": self.semantic_search.get_stats(),
            "embedder_stats": self.embedder.get_stats(),
        }


def initialize_demo_data(
    embedder: Optional[CodeEmbedder] = None,
    neo4j_driver: Optional[Any] = None,
    force_reload: bool = False,
) -> Dict[str, Any]:
    """
    Initialize demo data (convenience function).

    Args:
        embedder: Optional embedder instance
        neo4j_driver: Optional Neo4j driver
        force_reload: Whether to reload if already loaded

    Returns:
        Loading statistics
    """
    loader = DemoDataLoader(
        embedder=embedder,
        neo4j_driver=neo4j_driver,
    )

    # Check if already loaded
    if not force_reload and loader.is_demo_data_loaded():
        logger.info("Demo data already loaded")
        return {"status": "already_loaded"}

    # Clear and reload if force_reload
    if force_reload and loader.is_demo_data_loaded():
        logger.info("Force reload: clearing existing demo data")
        loader.clear_demo_data()

    # Load demo data
    return loader.load_all_demo_repositories()
