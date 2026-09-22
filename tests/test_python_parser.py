"""Tests for the Tree-sitter Python parser.

Covers fix #1: `from a.b import c, d` must keep the module path and the
imported names separate. Before the fix, every imported name overwrote
`module`, so the module path was lost and import edges resolved to nothing.
"""

import pytest

from app.services.parsers.python_parser import PythonParser


@pytest.fixture(scope="module")
def parser():
    return PythonParser()


class TestExtractImports:
    def test_plain_import_keeps_dotted_module(self, parser):
        imps = parser.extract_imports("import os.path\n", "x.py")
        assert [i.module for i in imps] == ["os.path"]
        assert imps[0].names == []

    def test_from_import_keeps_module_and_names(self, parser):
        imps = parser.extract_imports("from a.b import c, d as e\n", "x.py")
        assert len(imps) == 1
        assert imps[0].module == "a.b"
        assert imps[0].names == ["c", "d"]
        assert imps[0].alias == "e"

    def test_from_import_single_name(self, parser):
        imps = parser.extract_imports(
            "from app.services.parser import parse_repository\n", "x.py"
        )
        assert imps[0].module == "app.services.parser"
        assert imps[0].names == ["parse_repository"]

    def test_relative_import_keeps_dots(self, parser):
        imps = parser.extract_imports("from ..core import db\n", "pkg/api/x.py")
        assert imps[0].module == "..core"
        assert imps[0].names == ["db"]

    def test_bare_relative_import_keeps_dot(self, parser):
        imps = parser.extract_imports("from . import utils\n", "pkg/x.py")
        assert imps[0].module == "."
        assert imps[0].names == ["utils"]

    def test_relative_import_with_alias(self, parser):
        imps = parser.extract_imports("from ..core.db import get_driver as gd\n", "x.py")
        assert imps[0].module == "..core.db"
        assert imps[0].names == ["get_driver"]
        assert imps[0].alias == "gd"

    def test_wildcard_import_has_no_names(self, parser):
        imps = parser.extract_imports("from a.b import *\n", "x.py")
        assert imps[0].module == "a.b"
        assert imps[0].names == []

    def test_multiple_imports_are_all_returned(self, parser):
        src = "import os\nfrom a.b import c\nfrom . import d\n"
        imps = parser.extract_imports(src, "x.py")
        assert [i.module for i in imps] == ["os", "a.b", "."]
        assert [i.line_number for i in imps] == [1, 2, 3]


class TestExtractCalls:
    def test_calls_are_attributed_to_the_calling_function(self, parser):
        src = "def helper():\n    pass\n\ndef run():\n    helper()\n"
        calls = parser.extract_calls(src, "x.py")
        assert ("run", "helper") in {(c.caller, c.callee) for c in calls}

    def test_method_calls_are_reduced_to_the_attribute_name(self, parser):
        src = "def run():\n    self.helper()\n"
        calls = parser.extract_calls(src, "x.py")
        assert calls[0].callee == "helper"


class TestExtractFunctionsAndClasses:
    def test_functions_and_methods_are_extracted(self, parser):
        src = (
            "class Thing:\n"
            "    def method(self):\n"
            "        pass\n"
            "\n"
            "def top_level():\n"
            "    pass\n"
        )
        funcs = {f.name: f for f in parser.extract_functions(src, "x.py")}
        assert funcs["method"].is_method is True
        assert funcs["method"].class_name == "Thing"
        assert funcs["top_level"].is_method is False

    def test_class_inheritance_is_captured(self, parser):
        src = "class Child(Parent):\n    pass\n"
        classes = parser.extract_classes(src, "x.py")
        assert classes[0].base_classes == ["Parent"]
