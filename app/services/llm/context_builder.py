"""
Context builder for LLM chat - provides rich repository and node context.

This module queries Neo4j to build comprehensive context for the LLM,
including README content, file structure, node details, and relationships.
"""

import logging
from typing import Dict, List, Any, Optional

from app.db.neo4j_driver import run_query

logger = logging.getLogger(__name__)


def get_readme_for_repo(repo_id: str) -> str:
    """Get README content for a repository."""
    # Use toLower for case-insensitive type matching
    query = """
    MATCH (n:Node {repoId: $repoId})
    WHERE toLower(n.type) = 'readme'
    RETURN n.content as content
    LIMIT 1
    """
    try:
        result = run_query(query, {"repoId": repo_id})
        if result and len(result) > 0:
            return result[0].get("content", "") or ""
    except Exception as e:
        logger.warning(f"Failed to get README for {repo_id}: {e}")
    return ""


def get_repo_overview(repo_id: str) -> Dict[str, Any]:
    """
    Get high-level repository overview for LLM context.

    Returns:
        dict with readme, file_tree, entry_points, statistics, key_modules
    """
    overview = {
        "readme": "",
        "file_tree": [],
        "entry_points": [],
        "statistics": {
            "total_files": 0,
            "total_functions": 0,
            "total_classes": 0,
            "total_lines": 0,
            "languages": [],
        },
        "key_modules": [],
    }

    try:
        # Get README
        overview["readme"] = get_readme_for_repo(repo_id)

        # Get statistics (use toLower for case-insensitive type matching)
        stats_query = """
        MATCH (n:Node {repoId: $repoId})
        WITH toLower(n.type) as type, count(*) as cnt, sum(COALESCE(n.lineCount, 0)) as lines
        RETURN type, cnt, lines
        """
        stats_result = run_query(stats_query, {"repoId": repo_id})

        languages = set()
        for row in stats_result:
            node_type = row.get("type", "").lower()
            count = row.get("cnt", 0)
            lines = row.get("lines", 0)

            if node_type == "file":
                overview["statistics"]["total_files"] = count
            elif node_type == "function":
                overview["statistics"]["total_functions"] = count
            elif node_type == "class":
                overview["statistics"]["total_classes"] = count

            overview["statistics"]["total_lines"] += lines

        # Get file paths for tree (max 15, prioritize source files) - use toLower for case-insensitive type matching
        files_query = """
        MATCH (n:Node {repoId: $repoId})
        WHERE toLower(n.type) = 'file'
        AND NOT n.path =~ '(?i).*(test|spec|mock|fixture|__pycache__|node_modules|dist|build|coverage).*'
        RETURN n.path as path, n.lineCount as lineCount
        ORDER BY
            CASE
                WHEN n.path =~ '(?i)(src/|app/|lib/).*' THEN 0
                WHEN n.path =~ '(?i).*\\.(py|ts|tsx|js|jsx)$' THEN 1
                ELSE 2
            END,
            n.path
        LIMIT 15
        """
        files_result = run_query(files_query, {"repoId": repo_id})

        for row in files_result:
            path = row.get("path", "")
            if path:
                overview["file_tree"].append(path)
                # Detect language from extension
                if path.endswith(".py"):
                    languages.add("Python")
                elif path.endswith(".ts") or path.endswith(".tsx"):
                    languages.add("TypeScript")
                elif path.endswith(".js") or path.endswith(".jsx"):
                    languages.add("JavaScript")

        overview["statistics"]["languages"] = list(languages)

        # Detect entry points
        entry_patterns = ["main.py", "index.ts", "index.js", "app.py", "App.tsx", "App.jsx", "server.py", "server.ts"]
        for path in overview["file_tree"]:
            filename = path.split("/")[-1]
            if filename in entry_patterns:
                overview["entry_points"].append(path)

        # Get key modules (most connected files - files with most outgoing/incoming edges)
        # Use toLower for case-insensitive type matching
        key_modules_query = """
        MATCH (n:Node {repoId: $repoId})
        WHERE toLower(n.type) = 'file'
        OPTIONAL MATCH (n)-[r:RELATION]->()
        WITH n, count(r) as outgoing
        OPTIONAL MATCH ()-[r2:RELATION]->(n)
        WITH n, outgoing, count(r2) as incoming
        WITH n, outgoing + incoming as connections
        WHERE connections > 0
        RETURN n.path as path, n.name as name, connections
        ORDER BY connections DESC
        LIMIT 10
        """
        key_result = run_query(key_modules_query, {"repoId": repo_id})

        for row in key_result:
            overview["key_modules"].append({
                "path": row.get("path"),
                "name": row.get("name"),
                "connections": row.get("connections", 0),
            })

    except Exception as e:
        logger.error(f"Failed to get repo overview for {repo_id}: {e}")

    return overview


def get_node_full_context(repo_id: str, node_id: str) -> Optional[Dict[str, Any]]:
    """
    Get complete context for a specific node including relationships.

    Args:
        repo_id: Repository ID
        node_id: Node ID (format: repo_id:path:name)

    Returns:
        dict with node properties and all relationships
    """
    try:
        # Get node properties
        node_query = """
        MATCH (n:Node {id: $nodeId, repoId: $repoId})
        RETURN n.id as id, n.name as name, n.type as type, n.path as path,
               n.code as code, n.content as content, n.summary as summary,
               n.docstring as docstring, n.lineCount as lineCount,
               n.lineNumber as lineNumber, n.parameters as parameters,
               n.returnType as returnType, n.decorators as decorators,
               n.isAsync as isAsync, n.isPrivate as isPrivate,
               n.isStatic as isStatic, n.isMethod as isMethod,
               n.className as className, n.baseClasses as baseClasses,
               n.methods as methods, n.methodCount as methodCount,
               n.propertyCount as propertyCount, n.hasDocstring as hasDocstring,
               n.hasTypeHints as hasTypeHints
        """
        node_result = run_query(node_query, {"nodeId": node_id, "repoId": repo_id})

        if not node_result or len(node_result) == 0:
            return None

        node = dict(node_result[0])

        # Get outgoing relationships (what this node references)
        outgoing_query = """
        MATCH (n:Node {id: $nodeId})-[r:RELATION]->(target:Node)
        RETURN target.id as target_id, target.name as target_name,
               target.type as target_type, target.path as target_path,
               r.type as rel_type
        """
        outgoing = run_query(outgoing_query, {"nodeId": node_id})

        # Get incoming relationships (what references this node)
        incoming_query = """
        MATCH (source:Node)-[r:RELATION]->(n:Node {id: $nodeId})
        RETURN source.id as source_id, source.name as source_name,
               source.type as source_type, source.path as source_path,
               r.type as rel_type
        """
        incoming = run_query(incoming_query, {"nodeId": node_id})

        # Categorize relationships
        node["imports"] = []
        node["calls"] = []
        node["defines"] = []
        node["inherits_from"] = []
        node["imported_by"] = []
        node["called_by"] = []
        node["defined_in"] = None
        node["inherited_by"] = []

        for rel in outgoing:
            rel_type = rel.get("rel_type", "")
            target_info = {
                "name": rel.get("target_name"),
                "type": rel.get("target_type"),
                "path": rel.get("target_path"),
            }

            if rel_type == "imports":
                node["imports"].append(target_info)
            elif rel_type == "calls":
                node["calls"].append(target_info)
            elif rel_type == "defines":
                node["defines"].append(target_info)
            elif rel_type == "inherits":
                node["inherits_from"].append(target_info)

        for rel in incoming:
            rel_type = rel.get("rel_type", "")
            source_info = {
                "name": rel.get("source_name"),
                "type": rel.get("source_type"),
                "path": rel.get("source_path"),
            }

            if rel_type == "imports":
                node["imported_by"].append(source_info)
            elif rel_type == "calls":
                node["called_by"].append(source_info)
            elif rel_type == "defines":
                node["defined_in"] = source_info
            elif rel_type == "inherits":
                node["inherited_by"].append(source_info)

        return node

    except Exception as e:
        logger.error(f"Failed to get node context for {node_id}: {e}")
        return None


def get_call_graph(repo_id: str, function_name: str, depth: int = 2) -> Dict[str, Any]:
    """
    Get call graph centered on a function.

    Args:
        repo_id: Repository ID
        function_name: Function name to center the graph on
        depth: How many levels deep to traverse

    Returns:
        dict with function, callers, callees, and call_chain
    """
    result = {
        "function": function_name,
        "callers": [],
        "callees": [],
        "call_chain": "",
    }

    try:
        # Find the function node - use toLower for case-insensitive type matching
        func_query = """
        MATCH (n:Node {repoId: $repoId})
        WHERE toLower(n.type) = 'function' AND n.name = $name
        RETURN n.id as id, n.path as path
        LIMIT 1
        """
        func_result = run_query(func_query, {"repoId": repo_id, "name": function_name})

        if not func_result:
            return result

        func_id = func_result[0].get("id")
        func_path = func_result[0].get("path")

        # Get callers (functions that call this function)
        callers_query = """
        MATCH (caller:Node)-[r:RELATION {type: 'calls'}]->(n:Node {id: $funcId})
        RETURN caller.name as name, caller.path as path, caller.lineNumber as line
        LIMIT 10
        """
        callers = run_query(callers_query, {"funcId": func_id})
        result["callers"] = [{"name": c.get("name"), "file": c.get("path"), "line": c.get("line")} for c in callers]

        # Get callees (functions this function calls)
        callees_query = """
        MATCH (n:Node {id: $funcId})-[r:RELATION {type: 'calls'}]->(callee:Node)
        RETURN callee.name as name, callee.path as path, callee.lineNumber as line
        LIMIT 10
        """
        callees = run_query(callees_query, {"funcId": func_id})
        result["callees"] = [{"name": c.get("name"), "file": c.get("path"), "line": c.get("line")} for c in callees]

        # Build simple call chain text
        caller_names = [c["name"] for c in result["callers"][:3]]
        callee_names = [c["name"] for c in result["callees"][:3]]

        chain_parts = []
        if caller_names:
            chain_parts.append(f"[{', '.join(caller_names)}]")
            chain_parts.append("->")
        chain_parts.append(function_name)
        if callee_names:
            chain_parts.append("->")
            chain_parts.append(f"[{', '.join(callee_names)}]")

        result["call_chain"] = " ".join(chain_parts)

    except Exception as e:
        logger.error(f"Failed to get call graph for {function_name}: {e}")

    return result


# System prompt templates
SYSTEM_PROMPT_TEMPLATE = """You are RepoLens AI, a code analysis expert with COMPLETE ACCESS to this repository's structure and code.

CRITICAL: You have the full codebase context below. NEVER suggest running commands, exploring files, or using tools. Analyze ONLY what's provided.

## Your Capabilities
- Explain code architecture, patterns, and design decisions
- Trace data flow and function call chains
- Identify dependencies and coupling issues
- Explain what specific functions/classes do
- Suggest improvements based on the code you see
- Answer "how does X work" by referencing actual code

## Response Guidelines
1. ALWAYS reference specific files, functions, and line numbers
2. Quote actual code snippets when explaining
3. Use the relationship data (calls, imports, inheritance) to explain connections
4. If asked about code NOT in your context, say "I don't have that file/function in my current view. Try selecting it in the graph."
5. Be specific and technical - the user is a developer
6. **IMPORTANT**: When mentioning code elements (files, functions, classes), make them clickable using this format:
   - For files: [filename.py](node://repo_id:path/to/file.py)
   - For functions: [function_name](node://repo_id:path/to/file.py::func::function_name)
   - For classes: [ClassName](node://repo_id:path/to/file.py::class::ClassName)
   - Example: "The authentication is handled in [authenticate_user](node://repo-123:app/auth.py::func::authenticate_user)"

---

## Repository: {repo_name}

### README Summary
{readme_content}

### Structure ({file_count} files, {function_count} functions, {class_count} classes)
{file_tree}

### Entry Points
{entry_points}

### Key Modules (most connected)
{key_modules}

{node_context_section}
"""

NODE_CONTEXT_TEMPLATE = """
---
## Currently Selected: {node_name} ({node_type})

### Location
- File: {file_path}
- Lines: {line_number} ({line_count} lines)
- Language: {language}

### Code
```{language}
{code}
```

### Documentation
{docstring}

### Signature
- Parameters: {parameters}
- Returns: {return_type}
- Decorators: {decorators}
- Async: {is_async} | Private: {is_private} | Static: {is_static}

### Inheritance (if class)
- Extends: {base_classes}
- Methods: {methods}

### Relationships
**Imports:** {imports}
**Imported by:** {imported_by}
**Calls:** {calls}
**Called by:** {called_by}
**Defines:** {defines}
**Defined in:** {defined_in}
"""


def _format_list(items: List[Any], max_items: int = 10) -> str:
    """Format a list of items for display."""
    if not items:
        return "None"

    if isinstance(items[0], dict):
        names = [item.get("name", str(item)) for item in items[:max_items]]
    else:
        names = [str(item) for item in items[:max_items]]

    result = ", ".join(names)
    if len(items) > max_items:
        result += f" (+{len(items) - max_items} more)"
    return result


def _detect_language(path: str) -> str:
    """Detect language from file path."""
    if path.endswith(".py"):
        return "python"
    elif path.endswith(".ts") or path.endswith(".tsx"):
        return "typescript"
    elif path.endswith(".js") or path.endswith(".jsx"):
        return "javascript"
    return "text"


def build_system_prompt(
    repo_id: str,
    repo_name: str = "Repository",
    node_id: Optional[str] = None,
    max_readme_chars: int = 2000,
    max_code_chars: int = 2000,
) -> str:
    """
    Build the complete system prompt with repository and node context.

    Args:
        repo_id: Repository ID
        repo_name: Human-readable repository name
        node_id: Optional node ID to include detailed context for
        max_readme_chars: Maximum README characters to include
        max_code_chars: Maximum code characters to include

    Returns:
        Complete system prompt string
    """
    # Get repository overview
    overview = get_repo_overview(repo_id)

    # Truncate README
    readme_content = overview["readme"][:max_readme_chars]
    if len(overview["readme"]) > max_readme_chars:
        readme_content += "\n... (truncated)"

    # Format file tree
    file_tree = "\n".join(f"- {path}" for path in overview["file_tree"][:30])
    if len(overview["file_tree"]) > 30:
        file_tree += f"\n... and {len(overview['file_tree']) - 30} more files"

    # Format entry points
    entry_points = ", ".join(overview["entry_points"]) if overview["entry_points"] else "Not detected"

    # Format key modules
    key_modules = "\n".join(
        f"- {m['path']} ({m['connections']} connections)"
        for m in overview["key_modules"][:5]
    )
    if not key_modules:
        key_modules = "No highly connected modules detected"

    # Build node context section if node_id provided
    node_context_section = ""
    if node_id:
        node = get_node_full_context(repo_id, node_id)
        if node:
            language = _detect_language(node.get("path", ""))
            code = node.get("code") or node.get("content") or ""
            if len(code) > max_code_chars:
                code = code[:max_code_chars] + "\n... (truncated)"

            node_context_section = NODE_CONTEXT_TEMPLATE.format(
                node_name=node.get("name", "Unknown"),
                node_type=node.get("type", "Unknown"),
                file_path=node.get("path", "Unknown"),
                line_number=node.get("lineNumber", "?"),
                line_count=node.get("lineCount", "?"),
                language=language,
                code=code,
                docstring=node.get("docstring") or "No documentation",
                parameters=node.get("parameters") or "N/A",
                return_type=node.get("returnType") or "N/A",
                decorators=_format_list(node.get("decorators") or []),
                is_async=node.get("isAsync", False),
                is_private=node.get("isPrivate", False),
                is_static=node.get("isStatic", False),
                base_classes=_format_list(node.get("inherits_from") or node.get("baseClasses") or []),
                methods=_format_list(node.get("methods") or []),
                imports=_format_list(node.get("imports") or []),
                imported_by=_format_list(node.get("imported_by") or []),
                calls=_format_list(node.get("calls") or []),
                called_by=_format_list(node.get("called_by") or []),
                defines=_format_list(node.get("defines") or []),
                defined_in=node.get("defined_in", {}).get("name") if node.get("defined_in") else "N/A",
            )

    # Build final prompt
    stats = overview["statistics"]
    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        repo_name=repo_name,
        readme_content=readme_content or "No README available",
        file_count=stats["total_files"],
        function_count=stats["total_functions"],
        class_count=stats["total_classes"],
        file_tree=file_tree or "No files found",
        entry_points=entry_points,
        key_modules=key_modules,
        node_context_section=node_context_section,
    )

    return prompt
