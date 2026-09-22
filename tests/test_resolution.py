"""Tests for import and call resolution in app/services/parser.py.

Covers fix #5 (resolve calls the way the interpreter would, and leave
ambiguous calls unresolved) and the resolution of relative imports that
fix #1 made possible.

The node dicts here have the same shape the Tree-sitter parsers produce
(``ParseResult.to_neo4j_nodes``), including the capitalised ``type`` values.
"""

from app.services.parser import _resolve_calls, _resolve_imports, resolve_relative

REPO = "repo1"


def file_node(path):
    return {"id": f"{REPO}:{path}", "type": "File", "name": path.split("/")[-1], "path": path}


def func_node(path, name):
    return {"id": f"{REPO}:{path}:{name}", "type": "Function", "name": name, "path": path}


def import_edge(src_path, module, names=None, alias=None, eid="e1"):
    return {
        "id": eid,
        "source": f"{REPO}:{src_path}",
        "target": f"{REPO}:external:{module}",
        "type": "imports",
        "metadata": {"names": names or [], "alias": alias},
    }


def call_edge(src_path, caller, callee, eid="c1"):
    return {
        "id": eid,
        "source": f"{REPO}:{src_path}:{caller}",
        "target": f"{REPO}:external:{callee}",
        "type": "calls",
    }


def by_id(edges):
    return {e["id"]: e for e in edges}


class TestResolveRelative:
    def test_single_dot_stays_in_the_importers_folder(self):
        assert resolve_relative(".utils", "app/api/search.py") == "app.api.utils"

    def test_bare_dot_resolves_to_the_importers_package(self):
        assert resolve_relative(".", "app/api/search.py") == "app.api"

    def test_double_dot_goes_one_folder_up(self):
        assert resolve_relative("..core.db", "app/api/search.py") == "app.core.db"

    def test_windows_separators_are_normalised(self):
        assert resolve_relative("..core", "app\\api\\search.py") == "app.core"

    def test_too_many_dots_does_not_escape_the_repo(self):
        assert resolve_relative("....x", "app/x.py") == "x"


class TestResolveImports:
    def test_absolute_internal_import_resolves_to_the_file_node(self):
        nodes = [file_node("app/main.py"), file_node("app/services/parser.py")]
        edges = [import_edge("app/main.py", "app.services.parser", ["parse_repository"])]
        _, out = _resolve_imports(nodes, edges, REPO)
        assert out[0]["type"] == "imports"
        assert out[0]["target"] == f"{REPO}:app/services/parser.py"

    def test_relative_import_resolves_against_the_importing_file(self):
        nodes = [file_node("app/api/search.py"), file_node("app/core/db.py")]
        edges = [import_edge("app/api/search.py", "..core.db", ["get_driver"])]
        _, out = _resolve_imports(nodes, edges, REPO)
        assert out[0]["type"] == "imports"
        assert out[0]["target"] == f"{REPO}:app/core/db.py"

    def test_unknown_third_party_import_is_marked_external(self):
        nodes = [file_node("app/main.py")]
        edges = [import_edge("app/main.py", "fastapi", ["FastAPI"])]
        _, out = _resolve_imports(nodes, edges, REPO)
        assert out[0]["type"] == "external"

    def test_non_import_edges_pass_through_untouched(self):
        nodes = [file_node("a.py")]
        edges = [{"id": "d1", "source": f"{REPO}:a.py", "target": f"{REPO}:a.py:f", "type": "defines"}]
        _, out = _resolve_imports(nodes, edges, REPO)
        assert out == edges


class TestResolveCalls:
    def test_same_file_definition_wins_over_a_repo_wide_match(self):
        nodes = [
            file_node("a.py"), func_node("a.py", "run"), func_node("a.py", "helper"),
            file_node("b.py"), func_node("b.py", "helper"),
        ]
        edges = [call_edge("a.py", "run", "helper")]
        _, out = _resolve_calls(nodes, edges, REPO)
        assert out[0]["type"] == "calls"
        assert out[0]["target"] == f"{REPO}:a.py:helper"

    def test_imported_name_resolves_to_the_imported_file(self):
        nodes = [
            file_node("app/api.py"), func_node("app/api.py", "handler"),
            file_node("app/svc.py"), func_node("app/svc.py", "run"),
            file_node("app/other.py"), func_node("app/other.py", "run"),
        ]
        edges = [
            import_edge("app/api.py", "app.svc", ["run"], eid="i1"),
            call_edge("app/api.py", "handler", "run", eid="c1"),
        ]
        _, resolved = _resolve_imports(nodes, edges, REPO)
        _, out = _resolve_calls(nodes, resolved, REPO)
        assert by_id(out)["c1"]["target"] == f"{REPO}:app/svc.py:run"

    def test_aliased_import_resolves_through_the_alias(self):
        nodes = [
            file_node("app/api.py"), func_node("app/api.py", "handler"),
            file_node("app/svc.py"), func_node("app/svc.py", "run"),
        ]
        edges = [
            import_edge("app/api.py", "app.svc", ["run"], alias="go", eid="i1"),
            call_edge("app/api.py", "handler", "go", eid="c1"),
        ]
        _, resolved = _resolve_imports(nodes, edges, REPO)
        _, out = _resolve_calls(nodes, resolved, REPO)
        assert by_id(out)["c1"]["target"] == f"{REPO}:app/svc.py:run"

    def test_unique_repo_wide_match_resolves(self):
        nodes = [
            file_node("a.py"), func_node("a.py", "caller"),
            file_node("b.py"), func_node("b.py", "only_one"),
        ]
        edges = [call_edge("a.py", "caller", "only_one")]
        _, out = _resolve_calls(nodes, edges, REPO)
        assert out[0]["target"] == f"{REPO}:b.py:only_one"

    def test_ambiguous_call_is_left_unresolved_rather_than_guessed(self):
        """A missing edge is better than a wrong one."""
        nodes = [
            file_node("a.py"), func_node("a.py", "caller"),
            file_node("b.py"), func_node("b.py", "run"),
            file_node("c.py"), func_node("c.py", "run"),
        ]
        edges = [call_edge("a.py", "caller", "run")]
        _, out = _resolve_calls(nodes, edges, REPO)
        assert out[0]["type"] == "external"
        assert out[0]["target"] == f"{REPO}:external:run"

    def test_call_to_a_library_function_stays_external(self):
        nodes = [file_node("a.py"), func_node("a.py", "caller")]
        edges = [call_edge("a.py", "caller", "loads")]
        _, out = _resolve_calls(nodes, edges, REPO)
        assert out[0]["type"] == "external"


class TestEndToEndThreeFileRepo:
    """Parse three real files and assert the exact resolved edges."""

    def test_edges_across_a_tiny_repo(self):
        from app.services.parser import _extract_python_nodes

        sources = {
            "app/core/db.py": "def get_driver():\n    return 1\n",
            "app/svc.py": (
                "from app.core.db import get_driver\n"
                "\n"
                "def run():\n"
                "    return get_driver()\n"
            ),
            "app/api.py": (
                "from .svc import run\n"
                "\n"
                "def handler():\n"
                "    return run()\n"
            ),
        }

        nodes, edges, counter = [], [], 0
        for path, src in sources.items():
            n, e, counter = _extract_python_nodes(src, path, REPO, counter)
            nodes.extend(n)
            edges.extend(e)

        nodes, edges = _resolve_imports(nodes, edges, REPO)
        nodes, edges = _resolve_calls(nodes, edges, REPO)

        pairs = {(e["source"], e["target"], e["type"]) for e in edges}

        # svc.py imports core/db.py (absolute), api.py imports svc.py (relative)
        assert (f"{REPO}:app/svc.py", f"{REPO}:app/core/db.py", "imports") in pairs
        assert (f"{REPO}:app/api.py", f"{REPO}:app/svc.py", "imports") in pairs
        # run() calls get_driver() in another file, handler() calls run()
        assert (f"{REPO}:app/svc.py:run", f"{REPO}:app/core/db.py:get_driver", "calls") in pairs
        assert (f"{REPO}:app/api.py:handler", f"{REPO}:app/svc.py:run", "calls") in pairs
        # nothing in this repo should have fallen through to 'external'
        assert not [e for e in edges if e["type"] == "external"]


class TestJavaScriptRelativeImports:
    """JS/TS use relative *paths* ('../api/dashboard'), not dotted modules."""

    def test_sibling_directory_import_resolves(self):
        nodes = [
            file_node("src/components/Dashboard.tsx"),
            file_node("src/api/dashboard.ts"),
        ]
        edges = [import_edge("src/components/Dashboard.tsx", "../api/dashboard", ["fetchUserStats"])]
        _, out = _resolve_imports(nodes, edges, REPO)
        assert out[0]["type"] == "imports"
        assert out[0]["target"] == f"{REPO}:src/api/dashboard.ts"

    def test_same_directory_import_resolves(self):
        nodes = [file_node("src/components/Dashboard.tsx"), file_node("src/components/ui/Card.tsx")]
        edges = [import_edge("src/components/Dashboard.tsx", "./ui/Card", ["Card"])]
        _, out = _resolve_imports(nodes, edges, REPO)
        assert out[0]["target"] == f"{REPO}:src/components/ui/Card.tsx"

    def test_parent_directory_import_resolves(self):
        nodes = [file_node("src/api/dashboard.ts"), file_node("src/types.ts")]
        edges = [import_edge("src/api/dashboard.ts", "../types", ["UserStats"])]
        _, out = _resolve_imports(nodes, edges, REPO)
        assert out[0]["target"] == f"{REPO}:src/types.ts"

    def test_a_directory_import_resolves_to_its_index_file(self):
        nodes = [file_node("src/app.ts"), file_node("src/types/index.ts")]
        edges = [import_edge("src/app.ts", "./types", ["User"])]
        _, out = _resolve_imports(nodes, edges, REPO)
        assert out[0]["target"] == f"{REPO}:src/types/index.ts"

    def test_an_explicit_extension_still_resolves(self):
        nodes = [file_node("src/app.ts"), file_node("src/util.js")]
        edges = [import_edge("src/app.ts", "./util.js", ["helper"])]
        _, out = _resolve_imports(nodes, edges, REPO)
        assert out[0]["target"] == f"{REPO}:src/util.js"

    def test_an_unresolvable_relative_path_is_not_called_external(self):
        """It is internal-but-missing, not a third-party dependency."""
        nodes = [file_node("src/app.ts")]
        edges = [import_edge("src/app.ts", "./missing", ["x"])]
        _, out = _resolve_imports(nodes, edges, REPO)
        assert out[0]["type"] == "imports"

    def test_a_bare_package_import_is_still_external(self):
        nodes = [file_node("src/app.ts")]
        edges = [import_edge("src/app.ts", "react", ["useState"])]
        _, out = _resolve_imports(nodes, edges, REPO)
        assert out[0]["type"] == "external"
