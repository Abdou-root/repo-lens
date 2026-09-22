import os
import posixpath
import re
import shutil
import subprocess
import tempfile
import uuid
import logging
from typing import Callable, Dict, List, Optional, Tuple

# For Python AST parsing (legacy fallback)
import ast

logger = logging.getLogger(__name__)

# Tree-sitter parsers
from app.services.parsers.python_parser import PythonParser
from app.services.parsers.typescript_parser import (
    TypeScriptParser,
    JavaScriptParser,
    TSXParser,
    JSXParser,
)


def _safe_read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def _safe_cleanup(path: str) -> bool:
    """
    Safely remove a directory tree, logging any errors.

    Args:
        path: Directory path to remove

    Returns:
        True if cleanup succeeded, False otherwise
    """
    if not os.path.exists(path):
        return True
    try:
        shutil.rmtree(path)
        return True
    except Exception as e:
        logger.warning(f"Cleanup failed for {path}: {e}")
        return False


def _extract_python_nodes(content: str, relpath: str, repo_id: str, edge_counter: int = 0):
    """Extract Python nodes using Tree-sitter parser"""
    nodes = []
    edges = []
    tmp_path = None

    # Create a temporary file for the parser
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        # Use Tree-sitter parser, passing relpath as original_path for correct node IDs
        parser = PythonParser()
        result = parser.parse_file(tmp_path, original_path=relpath)

        # Convert to Neo4j format
        nodes = result.to_neo4j_nodes(repo_id)
        edges, next_counter = result.to_neo4j_edges(repo_id, edge_counter)

        return nodes, edges, next_counter
    except Exception as e:
        # Fallback to basic AST parsing on error
        logger.warning(f"Tree-sitter parsing failed for {relpath}, falling back to AST: {e}")
        return _extract_python_nodes_legacy(content, relpath, repo_id, edge_counter)
    finally:
        # Always clean up temp file
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def _extract_python_nodes_legacy(content: str, relpath: str, repo_id: str, edge_counter: int = 0):
    """Legacy AST-based parser (fallback)"""
    nodes = []
    edges = []
    try:
        tree = ast.parse(content)
    except Exception:
        return nodes, edges, edge_counter

    # file node
    file_id = f"{repo_id}:{relpath}"
    nodes.append({
        "id": file_id,
        "type": "file",
        "name": os.path.basename(relpath),
        "path": relpath,
        "summary": None,
        "lineCount": content.count("\n") + 1,
    })

    # imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                target = n.name
                edges.append({
                    "id": f"{repo_id}-e-{edge_counter}",
                    "source": file_id,
                    "target": target,
                    "type": "imports",
                })
                edge_counter += 1
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for n in node.names:
                target = (module + "." + n.name) if module else n.name
                edges.append({
                    "id": f"{repo_id}-e-{edge_counter}",
                    "source": file_id,
                    "target": target,
                    "type": "imports",
                })
                edge_counter += 1
        elif isinstance(node, ast.FunctionDef):
            func_id = f"{file_id}::func::{node.name}"
            nodes.append({
                "id": func_id,
                "type": "function",
                "name": node.name,
                "path": relpath,
                "summary": None,
                "lineCount": (node.end_lineno - node.lineno) if hasattr(node, "end_lineno") else None,
            })
            edges.append({
                "id": f"{repo_id}-e-{edge_counter}",
                "source": file_id,
                "target": func_id,
                "type": "defines",
            })
            edge_counter += 1
        elif isinstance(node, ast.ClassDef):
            cls_id = f"{file_id}::class::{node.name}"
            nodes.append({
                "id": cls_id,
                "type": "class",
                "name": node.name,
                "path": relpath,
                "summary": None,
                "lineCount": (node.end_lineno - node.lineno) if hasattr(node, "end_lineno") else None,
            })
            edges.append({
                "id": f"{repo_id}-e-{edge_counter}",
                "source": file_id,
                "target": cls_id,
                "type": "defines",
            })
            edge_counter += 1

    return nodes, edges, edge_counter


def _extract_ts_js_nodes(content: str, relpath: str, repo_id: str, edge_counter: int = 0):
    """Extract TypeScript/JavaScript nodes using Tree-sitter parser"""
    nodes = []
    edges = []
    tmp_path = None

    try:
        # Determine file extension to use correct parser
        ext = os.path.splitext(relpath)[1]

        # Select appropriate parser
        if ext == '.ts':
            parser = TypeScriptParser(is_typescript=True)
        elif ext == '.tsx':
            parser = TSXParser()
        elif ext == '.jsx':
            parser = JSXParser()
        else:  # .js
            parser = JavaScriptParser()

        # Create temp file with correct extension
        with tempfile.NamedTemporaryFile(mode='w', suffix=ext, delete=False, encoding='utf-8') as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        # Use Tree-sitter parser, passing relpath as original_path for correct node IDs
        result = parser.parse_file(tmp_path, original_path=relpath)

        # Convert to Neo4j format
        nodes = result.to_neo4j_nodes(repo_id)
        edges, next_counter = result.to_neo4j_edges(repo_id, edge_counter)

        return nodes, edges, next_counter
    except Exception as e:
        # Fallback to basic regex parsing on error
        logger.warning(f"Tree-sitter parsing failed for {relpath}, falling back to regex: {e}")
        return _extract_js_nodes_legacy(content, relpath, repo_id, edge_counter)
    finally:
        # Always clean up temp file
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


_js_import_re = re.compile(r"^\s*(?:import\s+(?:.+?)\s+from\s+['\"](?P<mod>[^'\"]+)['\"]|const\s+.+?=\s+require\(['\"](?P<req>[^'\"]+)['\"]\))", re.MULTILINE)


def _extract_js_nodes_legacy(content: str, relpath: str, repo_id: str, edge_counter: int = 0):
    """Legacy regex-based parser (fallback)"""
    nodes = []
    edges = []

    file_id = f"{repo_id}:{relpath}"
    nodes.append({
        "id": file_id,
        "type": "file",
        "name": os.path.basename(relpath),
        "path": relpath,
        "summary": None,
        "lineCount": content.count("\n") + 1,
    })

    for m in _js_import_re.finditer(content):
        mod = m.group("mod") or m.group("req")
        if mod:
            edges.append({
                "id": f"{repo_id}-e-{edge_counter}",
                "source": file_id,
                "target": mod,
                "type": "imports",
            })
            edge_counter += 1

    # Very naive function/class detection
    for m in re.finditer(r"function\s+(\w+)", content):
        name = m.group(1)
        func_id = f"{file_id}::func::{name}"
        nodes.append({
            "id": func_id,
            "type": "function",
            "name": name,
            "path": relpath,
            "summary": None,
            "lineCount": None,
        })
        edges.append({
            "id": f"{repo_id}-e-{edge_counter}",
            "source": file_id,
            "target": func_id,
            "type": "defines",
        })
        edge_counter += 1

    for m in re.finditer(r"class\s+(\w+)", content):
        name = m.group(1)
        cls_id = f"{file_id}::class::{name}"
        nodes.append({
            "id": cls_id,
            "type": "class",
            "name": name,
            "path": relpath,
            "summary": None,
            "lineCount": None,
        })
        edges.append({
            "id": f"{repo_id}-e-{edge_counter}",
            "source": file_id,
            "target": cls_id,
            "type": "defines",
        })
        edge_counter += 1

    return nodes, edges, edge_counter


# =============================================================================
# Performance & Directory Detection
# =============================================================================

# Directories to skip during file collection
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".nuxt", "coverage", ".pytest_cache",
    ".mypy_cache", "eggs", ".egg-info", ".tox", ".cache", ".parcel-cache",
    "vendor", "bower_components", ".svn", ".hg", "target",  # Rust/Java
}

# Environment-configurable limits
MAX_DEPTH = int(os.getenv("REPOLENS_MAX_DEPTH", "10"))
MAX_FILES = int(os.getenv("REPOLENS_MAX_FILES", "1000"))


def _detect_source_root(repo_root: str) -> str:
    """
    Detect the actual source root directory.

    Strategy:
    1. Check config files (package.json, pyproject.toml) for source hints
    2. Fallback to common source directories (src/, lib/, app/)
    3. Default to repo root
    """
    import json

    # Check package.json for source hints
    package_json_path = os.path.join(repo_root, "package.json")
    if os.path.exists(package_json_path):
        try:
            with open(package_json_path, "r", encoding="utf-8") as f:
                pkg = json.load(f)

            # Check for common source indicators
            if "workspaces" in pkg:
                # Monorepo - stay at root
                pass
            elif "main" in pkg:
                main_dir = os.path.dirname(pkg["main"])
                if main_dir and os.path.isdir(os.path.join(repo_root, main_dir)):
                    candidate = os.path.join(repo_root, main_dir)
                    if _has_code_files(candidate):
                        return candidate
        except Exception:
            pass

    # Check pyproject.toml for src layout hint
    pyproject_path = os.path.join(repo_root, "pyproject.toml")
    if os.path.exists(pyproject_path):
        try:
            content = _safe_read_text(pyproject_path)
            # Simple check for src-layout pattern
            if "packages = " in content and '"src"' in content:
                src_path = os.path.join(repo_root, "src")
                if os.path.isdir(src_path) and _has_code_files(src_path):
                    return src_path
        except Exception:
            pass

    # Fallback: check common source directories
    common_source_dirs = ["src", "lib", "app", "packages", "source"]
    for src_dir in common_source_dirs:
        candidate = os.path.join(repo_root, src_dir)
        if os.path.isdir(candidate) and _has_code_files(candidate):
            logger.info(f"Detected source root: {src_dir}/")
            return candidate

    # Default: use repo root
    return repo_root


def _has_code_files(directory: str, exts: set = None) -> bool:
    """Check if a directory contains code files (non-recursive, quick check)."""
    if exts is None:
        exts = {".py", ".js", ".ts", ".jsx", ".tsx"}

    try:
        with os.scandir(directory) as it:
            for entry in it:
                if entry.is_file():
                    if os.path.splitext(entry.name)[1] in exts:
                        return True
                elif entry.is_dir() and entry.name not in SKIP_DIRS:
                    # Check one level deep
                    try:
                        with os.scandir(entry.path) as sub_it:
                            for sub_entry in sub_it:
                                if sub_entry.is_file():
                                    if os.path.splitext(sub_entry.name)[1] in exts:
                                        return True
                    except (PermissionError, OSError):
                        continue
    except (PermissionError, OSError):
        pass

    return False


def _fast_collect_files(
    root: str,
    exts: set,
    skip_dirs: set = None,
    max_depth: int = None,
    max_files: int = None,
) -> List[str]:
    """
    Fast, non-recursive file collection using os.scandir with depth limiting.

    2-10x faster than os.walk() for large directories.
    """
    if skip_dirs is None:
        skip_dirs = SKIP_DIRS
    if max_depth is None:
        max_depth = MAX_DEPTH
    if max_files is None:
        max_files = MAX_FILES

    files = []
    stack = [(root, 0)]  # (path, depth)

    while stack and len(files) < max_files:
        current_path, depth = stack.pop()

        if depth > max_depth:
            continue

        try:
            with os.scandir(current_path) as it:
                for entry in it:
                    if len(files) >= max_files:
                        break

                    if entry.is_dir(follow_symlinks=False):
                        # Skip hidden directories and known skip dirs
                        if entry.name.startswith('.') or entry.name in skip_dirs:
                            continue
                        # Also skip directories ending with common patterns
                        if entry.name.endswith('.egg-info'):
                            continue
                        stack.append((entry.path, depth + 1))
                    elif entry.is_file():
                        ext = os.path.splitext(entry.name)[1]
                        if ext in exts:
                            files.append(entry.path)
        except (PermissionError, OSError) as e:
            logger.debug(f"Skipping directory {current_path}: {e}")
            continue

    if len(files) >= max_files:
        logger.warning(f"File limit reached ({max_files}). Some files may be skipped.")

    return files


def _prioritize_source_files(files: List[str], max_files: int) -> List[str]:
    """
    Prioritize source files when we have too many.

    Priority order:
    1. Files in src/ or similar directories
    2. Other code files
    """
    if len(files) <= max_files:
        return files

    # Prioritize src/ files
    src_patterns = ['/src/', '\\src\\', '/lib/', '\\lib\\', '/app/', '\\app\\']
    src_files = []
    other_files = []

    for f in files:
        if any(p in f for p in src_patterns):
            src_files.append(f)
        else:
            other_files.append(f)

    # Take src files first, then fill with others
    result = src_files[:max_files]
    remaining = max_files - len(result)
    if remaining > 0:
        result.extend(other_files[:remaining])

    logger.warning(f"Large repo detected ({len(files)} files), sampling {len(result)} prioritizing src/")
    return result


def _clone_repo(
    url: str,
    dest: str,
    progress_callback: Optional[Callable[[str], None]] = None,
    max_retries: int = 3,
    base_timeout: int = 180,
) -> bool:
    """Clone a git repository with retry logic and progress reporting.

    Args:
        url: Git repository URL
        dest: Destination directory
        progress_callback: Optional callback for progress messages
        max_retries: Maximum number of retry attempts (default 3)
        base_timeout: Base timeout in seconds (default 180s, increased for reliability)

    Returns:
        True if clone succeeded, False otherwise
    """
    import time

    # Retry delays with exponential backoff (5s, 15s, 30s)
    retry_delays = [5, 15, 30]

    # Transient error patterns that warrant retry
    transient_errors = [
        "Could not resolve host",
        "Connection timed out",
        "Connection refused",
        "SSL_ERROR",
        "Network is unreachable",
        "Unable to connect",
        "Operation timed out",
        "early EOF",
        "Connection reset by peer",
        "The requested URL returned error: 5",  # 5xx errors
        "unable to access",
        "Failed to connect",
    ]

    def is_transient_error(error_msg: str) -> bool:
        """Check if error is transient and worth retrying."""
        error_lower = error_msg.lower()
        return any(pattern.lower() in error_lower for pattern in transient_errors)

    def report_progress(message: str):
        """Report progress via callback and logger."""
        logger.info(message)
        if progress_callback:
            try:
                progress_callback(message)
            except Exception:
                pass  # Don't let callback errors affect clone

    last_error = None

    for attempt in range(max_retries):
        attempt_num = attempt + 1

        if attempt > 0:
            delay = retry_delays[min(attempt - 1, len(retry_delays) - 1)]
            report_progress(f"Retrying clone in {delay}s (attempt {attempt_num}/{max_retries})...")
            time.sleep(delay)

        try:
            report_progress(f"Cloning repository... (attempt {attempt_num}/{max_retries})")
            start_time = time.time()

            # Use shallow clone with optimizations for faster/more reliable clone
            result = subprocess.run(
                [
                    "git",
                    "-c", "http.version=HTTP/1.1",      # Avoid HTTP/2 issues
                    "-c", "core.compression=0",         # Reduce CPU stalls
                    "-c", "http.postBuffer=524288000",  # 500MB buffer for large repos
                    "-c", "http.lowSpeedLimit=1000",    # Fail if < 1KB/s
                    "-c", "http.lowSpeedTime=60",       # ...for 60 seconds
                    "clone",
                    "--depth", "1",
                    "--single-branch",
                    "--no-tags",
                    "--filter=blob:none",              # Partial clone - 20% faster
                    "--progress",                       # Show progress
                    url,
                    dest,
                ],
                check=True,
                timeout=base_timeout,
                capture_output=True,
                text=True,
            )

            elapsed = time.time() - start_time
            report_progress(f"Clone completed in {elapsed:.1f}s")
            logger.info(f"Git clone completed in {elapsed:.1f}s for {url}")
            return True

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            last_error = f"Clone timed out after {elapsed:.1f}s"
            logger.warning(f"Git clone attempt {attempt_num} timed out for {url}")

            # Cleanup partial clone before retry
            _safe_cleanup(dest)

            # Timeout is always worth retrying
            continue

        except subprocess.CalledProcessError as e:
            elapsed = time.time() - start_time
            error_msg = e.stderr or str(e)
            last_error = f"Clone failed: {error_msg[:200]}"
            logger.warning(f"Git clone attempt {attempt_num} failed for {url}: {error_msg}")

            # Cleanup partial clone before retry
            _safe_cleanup(dest)

            # Only retry if it's a transient error
            if not is_transient_error(error_msg):
                logger.error(f"Non-transient git error for {url}, not retrying: {error_msg}")
                report_progress(f"Clone failed: {error_msg[:100]}")
                return False

            continue

        except Exception as e:
            last_error = f"Unexpected error: {str(e)}"
            logger.error(f"Unexpected error cloning {url}: {e}")

            # Cleanup on unexpected error
            _safe_cleanup(dest)

            # Don't retry unknown errors
            report_progress(f"Clone failed: {str(e)[:100]}")
            return False

    # All retries exhausted
    logger.error(f"Git clone failed after {max_retries} attempts for {url}: {last_error}")
    report_progress(f"Clone failed after {max_retries} attempts: {last_error[:100]}")
    return False


def _read_readme(repo_dir: str, max_chars: int = 5000) -> str:
    """Read README file from repository root."""
    readme_names = ["README.md", "readme.md", "README", "README.rst", "README.txt"]
    for name in readme_names:
        readme_path = os.path.join(repo_dir, name)
        if os.path.exists(readme_path):
            try:
                with open(readme_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()[:max_chars]
            except Exception as e:
                logger.warning(f"Failed to read README at {readme_path}: {e}")
    return ""


async def parse_repository(
    repo_id: str,
    url: str,
    options: Optional[Dict] = None,
    progress_callback: Optional[Callable[[int, int, Optional[str]], None]] = None,
) -> Tuple[List[Dict], List[Dict]]:
    """Clone and parse a repository. Returns (nodes, edges).

    The returned nodes include a special 'readme' type node containing the README content.

    progress_callback(current, total, message)

    Features:
    - Smart source root detection (checks package.json, pyproject.toml, common dirs)
    - Fast file collection with os.scandir (2-10x faster than os.walk)
    - Depth limiting to avoid deep recursion in large repos
    - File count limiting with priority sampling
    - Configurable via REPOLENS_MAX_DEPTH and REPOLENS_MAX_FILES env vars
    - README.md extraction for LLM context
    """
    tmpdir = tempfile.mkdtemp(prefix=f"repolens_{repo_id}_")
    try:
        # Create clone progress callback to report to the main progress callback
        def clone_progress(message: str):
            if progress_callback:
                # Report clone progress as step 0 (before file parsing starts)
                progress_callback(0, 100, message)

        ok = await __clone_async(url, tmpdir, clone_progress)
        if not ok:
            raise RuntimeError("git clone failed")

        # Read README before processing files
        readme_content = _read_readme(tmpdir)

        # Detect source root (src/, lib/, app/, or repo root)
        source_root = _detect_source_root(tmpdir)
        if source_root != tmpdir:
            logger.info(f"Using detected source root: {os.path.relpath(source_root, tmpdir)}")

        # Collect source files using fast scandir-based collection
        exts = {".py", ".js", ".ts", ".jsx", ".tsx"}
        files = _fast_collect_files(
            root=source_root,
            exts=exts,
            skip_dirs=SKIP_DIRS,
            max_depth=MAX_DEPTH,
            max_files=MAX_FILES * 2,  # Collect more, then prioritize
        )

        # Prioritize source files if we have too many
        files = _prioritize_source_files(files, MAX_FILES)

        total = len(files) or 1
        nodes: List[Dict] = []
        edges: List[Dict] = []
        global_edge_counter = 0  # Global counter for edge IDs across all files

        for i, abs_path in enumerate(files, start=1):
            # Use source_root for relative paths (cleaner paths)
            relpath = os.path.relpath(abs_path, tmpdir).replace("\\", "/")
            if progress_callback:
                progress_callback(i, total, f"Parsing {relpath}")

            try:
                content = _safe_read_text(abs_path)
                ext = os.path.splitext(abs_path)[1]
                if ext == ".py":
                    n, e, global_edge_counter = _extract_python_nodes(content, relpath, repo_id, global_edge_counter)
                else:
                    # Use Tree-sitter for TypeScript/JavaScript files
                    n, e, global_edge_counter = _extract_ts_js_nodes(content, relpath, repo_id, global_edge_counter)

                nodes.extend(n)
                edges.extend(e)
            except Exception as e:
                # Log warning and continue with next file
                logger.warning(f"Failed to parse {relpath}: {e}")
                continue

        # Post-process: resolve imports to actual file nodes
        nodes, edges = _resolve_imports(nodes, edges, repo_id)

        # Post-process: resolve call edges to actual function nodes
        nodes, edges = _resolve_calls(nodes, edges, repo_id)

        # Add README as a special node for LLM context
        if readme_content:
            readme_node = {
                "id": f"{repo_id}:README",
                "type": "readme",
                "name": "README",
                "path": "README.md",
                "content": readme_content,
                "lineCount": len(readme_content.splitlines()),
            }
            nodes.append(readme_node)
            logger.info(f"Added README node ({len(readme_content)} chars) for {repo_id}")

        return nodes, edges
    finally:
        # cleanup clone directory
        _safe_cleanup(tmpdir)


def resolve_relative(module: str, importer_path: str) -> str:
    """
    Turn a relative import into an absolute dotted module path.

    '..core.db' imported from 'app/api/search.py' -> 'app.core.db'
    '.' imported from 'app/api/search.py'         -> 'app.api'
    """
    dots = len(module) - len(module.lstrip("."))
    if dots == 0:
        return module

    # Folder of the importing file, then one level up per extra dot
    base = importer_path.replace("\\", "/").split("/")[:-1]
    if dots > 1:
        base = base[: max(0, len(base) - (dots - 1))]

    rest = module.lstrip(".")
    return ".".join(base + ([rest] if rest else []))


# Extensions a JS/TS relative import may omit
JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")


def resolve_relative_path(module: str, importer_path: str) -> str:
    """
    Resolve a JS/TS relative import path against the importing file.

    '../api/dashboard' imported from 'src/components/Dashboard.tsx'
        -> 'src/api/dashboard'
    """
    base = posixpath.dirname(importer_path.replace("\\", "/"))
    joined = posixpath.normpath(posixpath.join(base, module))
    # normpath can produce a leading '..' when the import escapes the repo
    return joined.lstrip("./") if joined.startswith((".", "/")) else joined


def _js_import_candidates(path: str):
    """The files a JS/TS import path may refer to, most specific first."""
    yield path
    for ext in JS_EXTENSIONS:
        yield path + ext
    for ext in JS_EXTENSIONS:
        yield f"{path}/index{ext}"


def _module_name_for_path(path: str) -> str:
    """'src/utils/parser.py' -> 'src.utils.parser'"""
    module_name = path.replace("\\", "/").replace("/", ".")
    for ext in (".tsx", ".jsx", ".py", ".ts", ".js"):
        if module_name.endswith(ext):
            return module_name[: -len(ext)]
    return module_name


def _path_from_source_id(source_id: str, repo_id: str) -> str:
    """'repo1:app/api/search.py' or 'repo1:app/api/search.py:run' -> 'app/api/search.py'"""
    rest = source_id.split(f"{repo_id}:", 1)[-1]
    # Node ids are '<repo>:<path>' for files and '<repo>:<path>:<name>' for
    # classes and functions, so drop a trailing ':<name>' segment if present.
    if ":" in rest:
        head, tail = rest.rsplit(":", 1)
        if "/" not in tail and "." in head:
            return head
    return rest


def _resolve_imports(
    nodes: List[Dict],
    edges: List[Dict],
    repo_id: str,
) -> Tuple[List[Dict], List[Dict]]:
    """
    Resolve import edges to actual file nodes where possible.

    For each 'imports' edge:
    - If target matches a file node, keep as 'imports'
    - If target is a relative import, resolve it against the importing file
    - If target is an external package (npm, pip), mark as 'external'
    """
    # Build a lookup of file nodes by path and module name
    file_nodes = {}
    module_to_file = {}
    partial_to_file = {}

    for node in nodes:
        if str(node.get("type", "")).lower() != "file":
            continue

        path = node.get("path", "")
        node_id = node.get("id", "")

        # Store by full path
        file_nodes[path] = node_id

        # Also store by module name (without extension)
        module_name = _module_name_for_path(path)
        module_to_file[module_name] = node_id

        # Also store without leading path segments, but keep these in a
        # separate, lower-priority map so a suffix match never shadows a
        # full module path.
        parts = module_name.split(".")
        for i in range(1, len(parts)):
            partial = ".".join(parts[i:])
            if partial not in partial_to_file:
                partial_to_file[partial] = node_id

    # Known external packages (npm)
    npm_packages = {
        "react", "react-dom", "next", "vue", "angular", "express", "axios",
        "lodash", "moment", "dayjs", "date-fns", "uuid", "zod", "yup",
        "@", "lucide-react", "tailwindcss", "framer-motion", "zustand",
    }

    # Known external packages (Python)
    python_packages = {
        "os", "sys", "json", "re", "typing", "datetime", "pathlib", "logging",
        "collections", "itertools", "functools", "ast", "subprocess", "tempfile",
        "hashlib", "base64", "urllib", "http", "socket", "threading", "asyncio",
        "numpy", "pandas", "requests", "flask", "django", "fastapi", "pydantic",
        "sqlalchemy", "redis", "celery", "pytest", "unittest", "openai", "tiktoken",
    }

    def lookup(module: str) -> Optional[str]:
        if module in file_nodes:
            return file_nodes[module]
        if module in module_to_file:
            return module_to_file[module]
        return partial_to_file.get(module)

    resolved_edges = []
    for edge in edges:
        if edge.get("type") != "imports":
            resolved_edges.append(edge)
            continue

        target = edge.get("target", "")
        module = target.split(f"{repo_id}:external:", 1)[-1]

        # Relative imports: resolve against the folder of the importing file
        if module.startswith("."):
            importer = _path_from_source_id(edge.get("source", ""), repo_id)

            if "/" in module:
                # JS/TS style relative path: './ui/Card', '../api/dashboard'
                resolved_path = resolve_relative_path(module, importer)
                node_id = next(
                    (file_nodes[c] for c in _js_import_candidates(resolved_path)
                     if c in file_nodes),
                    None,
                )
                absolute = resolved_path
            else:
                # Python style relative module: '.svc', '..core.db'
                absolute = resolve_relative(module, importer)
                node_id = lookup(absolute)

            if node_id:
                edge["target"] = node_id
            else:
                # Internal but unresolved: keep it as 'imports' so the edge is
                # not misreported as a third-party dependency.
                edge.setdefault("metadata", {})["module"] = absolute
            resolved_edges.append(edge)
            continue

        node_id = lookup(module)
        if node_id:
            edge["target"] = node_id
            resolved_edges.append(edge)
            continue

        # Check if it's an external package
        root = module.split(".")[0]
        is_external = (
            module.startswith("@")
            or root in npm_packages
            or root in python_packages
            # Non-relative imports that match no file are likely external,
            # unless they look like they point at a source directory.
            or not any(module.startswith(d) for d in ["src", "lib", "app", "components"])
        )

        if is_external:
            edge["type"] = "external"

        resolved_edges.append(edge)

    return nodes, resolved_edges


def _resolve_calls(
    nodes: List[Dict],
    edges: List[Dict],
    repo_id: str,
) -> Tuple[List[Dict], List[Dict]]:
    """
    Resolve 'calls' edges to actual function nodes.

    Resolution follows the order a Python interpreter would use:
      1. a function defined in the same file
      2. a name imported into that file (``from mod import callee``)
      3. a name that is unique across the whole repository

    If none of those apply the call is ambiguous, and the edge is left
    'external' rather than pointed at an arbitrary same-named function.
    A missing edge is better than a wrong one.
    """
    # {path: {function_name: node_id}}
    funcs_by_file: Dict[str, Dict[str, str]] = {}
    # {function_name: [node_id, ...]}
    funcs_by_name: Dict[str, List[str]] = {}
    # {node_id: path} for file nodes, used to follow resolved import edges
    path_by_file_id: Dict[str, str] = {}

    for node in nodes:
        node_type = str(node.get("type", "")).lower()
        if node_type == "file":
            path_by_file_id[node.get("id", "")] = node.get("path", "")
        elif node_type == "function":
            name = node.get("name", "")
            node_id = node.get("id", "")
            path = node.get("path", "")
            if not name or not node_id:
                continue
            funcs_by_file.setdefault(path, {})[name] = node_id
            funcs_by_name.setdefault(name, []).append(node_id)

    # {importer_path: [{'names': [...], 'alias': str|None, 'path': target path}]}
    imports_by_file: Dict[str, List[Dict]] = {}
    for edge in edges:
        if edge.get("type") != "imports":
            continue
        importer = _path_from_source_id(edge.get("source", ""), repo_id)
        target_path = path_by_file_id.get(edge.get("target", ""))
        if not target_path:
            continue  # unresolved or external import: nothing to look into
        metadata = edge.get("metadata") or {}
        imports_by_file.setdefault(importer, []).append({
            "names": metadata.get("names") or [],
            "alias": metadata.get("alias"),
            "path": target_path,
        })

    def resolve_callee(callee: str, caller_file: str) -> Optional[str]:
        # 1. defined in the same file
        same_file = funcs_by_file.get(caller_file, {})
        if callee in same_file:
            return same_file[callee]

        # 2. imported by name into this file: from mod import callee
        for imp in imports_by_file.get(caller_file, []):
            if callee in imp["names"] or callee == imp["alias"]:
                target_funcs = funcs_by_file.get(imp["path"], {})
                # An aliased import points at the single imported name
                original = callee
                if callee == imp["alias"] and imp["names"]:
                    original = imp["names"][0]
                if original in target_funcs:
                    return target_funcs[original]

        # 3. unique across the whole repo
        matches = funcs_by_name.get(callee, [])
        if len(matches) == 1:
            return matches[0]

        # ambiguous or unknown
        return None

    resolved_edges = []
    for edge in edges:
        if edge.get("type") != "calls":
            resolved_edges.append(edge)
            continue

        target = edge.get("target", "")
        if ":external:" in target:
            callee = target.split(":external:")[-1]
        else:
            callee = target

        caller_file = _path_from_source_id(edge.get("source", ""), repo_id)
        node_id = resolve_callee(callee, caller_file)

        if node_id:
            edge["target"] = node_id
        else:
            edge["type"] = "external"

        resolved_edges.append(edge)

    return nodes, resolved_edges


async def __clone_async(
    url: str,
    dest: str,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> bool:
    """Run blocking clone in thread with progress callback support."""
    import asyncio

    return await asyncio.to_thread(_clone_repo, url, dest, progress_callback)
