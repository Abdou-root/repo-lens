"""
Base parser interface and data models for code parsing.

This module defines the abstract base class for language-specific parsers
and the data structures used to represent parsed code elements.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path


@dataclass
class Import:
    """Represents an import statement"""
    module: str  # Module being imported (e.g., "os", "fastapi")
    names: List[str]  # Specific names imported (e.g., ["FastAPI", "Request"])
    alias: Optional[str] = None  # Alias if using "as" (e.g., "pd" for pandas)
    file_path: str = ""
    line_number: int = 0


@dataclass
class ClassDef:
    """Represents a class definition"""
    name: str
    base_classes: List[str]  # Parent classes for inheritance tracking
    methods: List[str]  # Method names defined in this class
    docstring: Optional[str] = None
    decorators: List[str] = None  # Class decorators
    file_path: str = ""
    line_number: int = 0
    line_count: int = 0
    code: str = ""  # Full class code for embedding
    # Additional metrics
    method_count: int = 0
    property_count: int = 0
    has_docstring: bool = False


@dataclass
class FunctionDef:
    """Represents a function or method definition"""
    name: str
    parameters: List[Dict[str, Any]]  # [{name: str, type: Optional[str], default: Optional[str]}]
    return_type: Optional[str] = None
    docstring: Optional[str] = None
    decorators: List[str] = None  # Function decorators
    is_method: bool = False  # True if this is a class method
    class_name: Optional[str] = None  # Parent class if is_method=True
    file_path: str = ""
    line_number: int = 0
    line_count: int = 0
    code: str = ""  # Full function code for embedding
    # Additional metrics
    is_async: bool = False
    is_private: bool = False  # Starts with _ or __
    is_static: bool = False  # Has @staticmethod
    has_docstring: bool = False
    has_type_hints: bool = False  # Has typed parameters or return type
    parameter_count: int = 0


@dataclass
class CallSite:
    """Represents a function call for call graph analysis"""
    caller: str  # Function/method making the call
    callee: str  # Function/method being called
    file_path: str = ""
    line_number: int = 0


@dataclass
class ApiCall:
    """Represents an API call for cross-language tracking"""
    caller: str  # Function/component making the API call
    endpoint: str  # API endpoint (e.g., "/api/repos")
    method: str  # HTTP method (GET, POST, PUT, DELETE, etc.)
    file_path: str = ""
    line_number: int = 0


@dataclass
class ParseResult:
    """Container for all parsed elements from a file"""
    file_path: str
    imports: List[Import]
    classes: List[ClassDef]
    functions: List[FunctionDef]
    calls: List[CallSite]
    language: str  # e.g., "python", "typescript"
    api_calls: List[ApiCall] = field(default_factory=list)  # API calls for cross-language tracking
    line_count: int = 0

    def to_neo4j_nodes(self, repo_id: str) -> List[Dict[str, Any]]:
        """Convert parsed elements to Neo4j node format"""
        nodes = []

        # File node
        nodes.append({
            'id': f"{repo_id}:{self.file_path}",
            'type': 'File',
            'name': Path(self.file_path).name,
            'path': self.file_path,
            'language': self.language,
            'lineCount': self.line_count,
            'repoId': repo_id,
        })

        # Class nodes
        for cls in self.classes:
            nodes.append({
                'id': f"{repo_id}:{self.file_path}:{cls.name}",
                'type': 'Class',
                'name': cls.name,
                'path': self.file_path,
                'lineNumber': cls.line_number,
                'lineCount': cls.line_count,
                'code': cls.code,
                'docstring': cls.docstring,
                'baseClasses': cls.base_classes,
                'repoId': repo_id,
                # Metrics
                'methodCount': cls.method_count,
                'propertyCount': cls.property_count,
                'hasDocstring': cls.has_docstring,
            })

        # Function nodes
        for func in self.functions:
            nodes.append({
                'id': f"{repo_id}:{self.file_path}:{func.name}",
                'type': 'Function',
                'name': func.name,
                'path': self.file_path,
                'lineNumber': func.line_number,
                'lineCount': func.line_count,
                'code': func.code,
                'docstring': func.docstring,
                'className': func.class_name,
                'isMethod': func.is_method,
                'repoId': repo_id,
                # Metrics
                'isAsync': func.is_async,
                'isPrivate': func.is_private,
                'isStatic': func.is_static,
                'hasDocstring': func.has_docstring,
                'hasTypeHints': func.has_type_hints,
                'parameterCount': func.parameter_count,
            })

        return nodes

    def to_neo4j_edges(self, repo_id: str, edge_counter_start: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        """Convert relationships to Neo4j edge format.

        Args:
            repo_id: Repository identifier
            edge_counter_start: Starting value for edge counter (for global uniqueness)

        Returns:
            Tuple of (edges list, next edge counter value)
        """
        edges = []
        edge_counter = edge_counter_start

        # File imports modules (external)
        for imp in self.imports:
            edges.append({
                'id': f"{repo_id}-edge-{edge_counter}",
                'source': f"{repo_id}:{self.file_path}",
                'target': f"{repo_id}:external:{imp.module}",
                'type': 'imports',
                'metadata': {
                    'names': imp.names,
                    'alias': imp.alias,
                }
            })
            edge_counter += 1

        # File defines classes
        for cls in self.classes:
            edges.append({
                'id': f"{repo_id}-edge-{edge_counter}",
                'source': f"{repo_id}:{self.file_path}",
                'target': f"{repo_id}:{self.file_path}:{cls.name}",
                'type': 'defines',
            })
            edge_counter += 1

        # File defines functions (top-level)
        for func in self.functions:
            if not func.is_method:
                edges.append({
                    'id': f"{repo_id}-edge-{edge_counter}",
                    'source': f"{repo_id}:{self.file_path}",
                    'target': f"{repo_id}:{self.file_path}:{func.name}",
                    'type': 'defines',
                })
                edge_counter += 1

        # Class defines methods
        for func in self.functions:
            if func.is_method and func.class_name:
                edges.append({
                    'id': f"{repo_id}-edge-{edge_counter}",
                    'source': f"{repo_id}:{self.file_path}:{func.class_name}",
                    'target': f"{repo_id}:{self.file_path}:{func.name}",
                    'type': 'defines',
                })
                edge_counter += 1

        # Inheritance edges
        for cls in self.classes:
            for base_class in cls.base_classes:
                edges.append({
                    'id': f"{repo_id}-edge-{edge_counter}",
                    'source': f"{repo_id}:{self.file_path}:{cls.name}",
                    'target': f"{repo_id}:external:{base_class}",  # Will resolve to actual class if in repo
                    'type': 'inherits',
                })
                edge_counter += 1

        # Call graph edges
        for call in self.calls:
            edges.append({
                'id': f"{repo_id}-edge-{edge_counter}",
                'source': f"{repo_id}:{self.file_path}:{call.caller}",
                'target': f"{repo_id}:external:{call.callee}",  # Will resolve to actual function if in repo
                'type': 'calls',
            })
            edge_counter += 1

        # API call edges (cross-language tracking)
        for api_call in self.api_calls:
            edges.append({
                'id': f"{repo_id}-edge-{edge_counter}",
                'source': f"{repo_id}:{self.file_path}:{api_call.caller}",
                'target': f"{repo_id}:api:{api_call.endpoint}",  # API endpoint as target
                'type': 'api_call',
                'metadata': {
                    'method': api_call.method,
                    'endpoint': api_call.endpoint,
                }
            })
            edge_counter += 1

        return edges, edge_counter


class LanguageParser(ABC):
    """Abstract base class for language-specific parsers"""

    @property
    @abstractmethod
    def language(self) -> str:
        """Return the language name (e.g., 'python', 'typescript')"""
        pass

    @abstractmethod
    def extract_imports(self, source_code: str, file_path: str) -> List[Import]:
        """Extract import statements from source code"""
        pass

    @abstractmethod
    def extract_classes(self, source_code: str, file_path: str) -> List[ClassDef]:
        """Extract class definitions from source code"""
        pass

    @abstractmethod
    def extract_functions(self, source_code: str, file_path: str) -> List[FunctionDef]:
        """Extract function definitions from source code"""
        pass

    @abstractmethod
    def extract_calls(self, source_code: str, file_path: str) -> List[CallSite]:
        """Extract function call sites for call graph analysis"""
        pass

    def parse_file(self, file_path: str, original_path: Optional[str] = None) -> ParseResult:
        """
        Parse a file and return all extracted elements.

        This is the main entry point for parsing. It reads the file,
        calls all extraction methods, and returns a ParseResult.

        Args:
            file_path: Path to the file to read (can be a temp file)
            original_path: Original file path to use for node IDs and paths.
                          If not provided, file_path is used. This is useful when
                          parsing temp files but wanting the original repo path in results.
        """
        # Use original_path for node IDs and paths, but file_path for reading
        effective_path = original_path or file_path

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            source_code = f.read()

        # Count lines
        line_count = len(source_code.splitlines())

        # Extract all elements using effective_path for correct node IDs
        imports = self.extract_imports(source_code, effective_path)
        classes = self.extract_classes(source_code, effective_path)
        functions = self.extract_functions(source_code, effective_path)
        calls = self.extract_calls(source_code, effective_path)

        # Extract API calls if the parser supports it (TypeScript/JavaScript)
        api_calls = []
        try:
            if hasattr(self, 'extract_api_calls') and callable(getattr(self, 'extract_api_calls')):
                api_calls_data = getattr(self, 'extract_api_calls')(source_code, effective_path)  # type: ignore
                # Convert dict format to ApiCall objects
                api_calls = [ApiCall(**call_data) for call_data in api_calls_data]
        except Exception:
            # API call extraction is optional and may fail
            pass

        return ParseResult(
            file_path=effective_path,
            imports=imports,
            classes=classes,
            functions=functions,
            calls=calls,
            api_calls=api_calls,
            language=self.language,
            line_count=line_count,
        )
