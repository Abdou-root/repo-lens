"""
Python parser using Tree-sitter for accurate AST traversal.

This parser extracts:
- Import statements (import, from...import, with aliases)
- Class definitions with inheritance
- Function/method definitions with decorators and docstrings
- Call graph (function invocations)
"""

import tree_sitter_python as tspython
from tree_sitter import Language, Parser, Node
from typing import List, Optional, Dict, Any
from pathlib import Path

from app.services.parsers.base import (
    LanguageParser,
    Import,
    ClassDef,
    FunctionDef,
    CallSite,
)


class PythonParser(LanguageParser):
    """Tree-sitter based Python parser"""

    def __init__(self):
        # Initialize Tree-sitter parser with Python language
        # For tree-sitter 0.21.x and tree-sitter-python 0.21.x
        PY_LANGUAGE = Language(tspython.language(), 'python')
        self.parser = Parser()
        self.parser.set_language(PY_LANGUAGE)
        self._current_class = None  # Track current class context for methods
        self._call_graph = []  # Track calls during traversal

    @property
    def language(self) -> str:
        return "python"

    def extract_imports(self, source_code: str, file_path: str) -> List[Import]:
        """Extract import statements"""
        tree = self.parser.parse(bytes(source_code, "utf8"))
        imports = []

        def visit_node(node: Node):
            # import module
            if node.type == "import_statement":
                for child in node.children:
                    if child.type == "dotted_name":
                        module = self._get_text(child, source_code)
                        imports.append(Import(
                            module=module,
                            names=[],
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                        ))

            # from module import names
            elif node.type == "import_from_statement":
                # The module path and the imported names are all `dotted_name`
                # nodes, so they can only be told apart by field name:
                # `from a.b import c, d` -> module_name=a.b, name=c, name=d.
                module_node = node.child_by_field_name("module_name")
                module = self._get_text(module_node, source_code) if module_node else None
                names = []
                alias = None

                for child in node.children_by_field_name("name"):
                    if child.type == "aliased_import":
                        name_node = child.child_by_field_name("name")
                        alias_node = child.child_by_field_name("alias")
                        if name_node:
                            names.append(self._get_text(name_node, source_code))
                        if alias_node:
                            alias = self._get_text(alias_node, source_code)
                    else:
                        # Plain dotted_name: from module import name1, name2
                        names.append(self._get_text(child, source_code))

                if module:
                    imports.append(Import(
                        module=module,
                        names=names,
                        alias=alias,
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                    ))

            # Recursively visit children
            for child in node.children:
                visit_node(child)

        visit_node(tree.root_node)
        return imports

    def extract_classes(self, source_code: str, file_path: str) -> List[ClassDef]:
        """Extract class definitions with inheritance"""
        tree = self.parser.parse(bytes(source_code, "utf8"))
        classes = []

        def visit_node(node: Node):
            if node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                if not name_node:
                    return

                class_name = self._get_text(name_node, source_code)

                # Extract base classes (inheritance)
                base_classes = []
                superclasses_node = node.child_by_field_name("superclasses")
                if superclasses_node:
                    for child in superclasses_node.children:
                        if child.type in ["identifier", "attribute"]:
                            base_classes.append(self._get_text(child, source_code))

                # Extract methods (functions inside class body)
                methods = []
                body_node = node.child_by_field_name("body")
                if body_node:
                    for child in body_node.children:
                        if child.type == "function_definition":
                            method_name_node = child.child_by_field_name("name")
                            if method_name_node:
                                methods.append(self._get_text(method_name_node, source_code))

                # Extract docstring
                docstring = self._extract_docstring(node, source_code)

                # Extract decorators
                decorators = self._extract_decorators(node, source_code)

                # Get full class code
                code = self._get_text(node, source_code)
                line_count = node.end_point[0] - node.start_point[0] + 1

                # Count properties (class-level variables)
                property_count = 0
                if body_node:
                    for child in body_node.children:
                        if child.type == "expression_statement":
                            for subchild in child.children:
                                if subchild.type == "assignment":
                                    property_count += 1

                classes.append(ClassDef(
                    name=class_name,
                    base_classes=base_classes,
                    methods=methods,
                    docstring=docstring,
                    decorators=decorators,
                    file_path=file_path,
                    line_number=node.start_point[0] + 1,
                    line_count=line_count,
                    code=code[:1000],  # Truncate for storage
                    # Metrics
                    method_count=len(methods),
                    property_count=property_count,
                    has_docstring=docstring is not None and len(docstring) > 0,
                ))

            # Recursively visit children
            for child in node.children:
                visit_node(child)

        visit_node(tree.root_node)
        return classes

    def extract_functions(self, source_code: str, file_path: str) -> List[FunctionDef]:
        """Extract function and method definitions"""
        tree = self.parser.parse(bytes(source_code, "utf8"))
        functions = []

        def visit_node(node: Node, parent_class: Optional[str] = None):
            if node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                if not name_node:
                    return

                func_name = self._get_text(name_node, source_code)

                # Extract parameters
                parameters = []
                params_node = node.child_by_field_name("parameters")
                if params_node:
                    for child in params_node.children:
                        if child.type == "identifier":
                            parameters.append({'name': self._get_text(child, source_code)})
                        elif child.type == "typed_parameter":
                            param_name_node = child.child_by_field_name("name")
                            param_type_node = child.child_by_field_name("type")
                            param_dict = {}
                            if param_name_node:
                                param_dict['name'] = self._get_text(param_name_node, source_code)
                            if param_type_node:
                                param_dict['type'] = self._get_text(param_type_node, source_code)
                            parameters.append(param_dict)
                        elif child.type == "default_parameter":
                            param_name_node = child.child_by_field_name("name")
                            param_default_node = child.child_by_field_name("value")
                            param_dict = {}
                            if param_name_node:
                                param_dict['name'] = self._get_text(param_name_node, source_code)
                            if param_default_node:
                                param_dict['default'] = self._get_text(param_default_node, source_code)
                            parameters.append(param_dict)

                # Extract return type
                return_type = None
                return_type_node = node.child_by_field_name("return_type")
                if return_type_node:
                    return_type = self._get_text(return_type_node, source_code)

                # Extract docstring
                docstring = self._extract_docstring(node, source_code)

                # Extract decorators
                decorators = self._extract_decorators(node, source_code)

                # Get full function code
                code = self._get_text(node, source_code)
                line_count = node.end_point[0] - node.start_point[0] + 1

                # Determine metrics
                is_async = 'async' in self._get_text(node.parent, source_code)[:20] if node.parent else False
                # Check for async def directly in the function definition
                for sibling in (node.parent.children if node.parent else []):
                    if sibling.type == 'async':
                        is_async = True
                        break

                is_private = func_name.startswith('_')
                is_static = decorators is not None and '@staticmethod' in decorators
                has_docstring = docstring is not None and len(docstring) > 0

                # Check for type hints
                has_type_hints = return_type is not None
                for param in parameters:
                    if param.get('type'):
                        has_type_hints = True
                        break

                functions.append(FunctionDef(
                    name=func_name,
                    parameters=parameters,
                    return_type=return_type,
                    docstring=docstring,
                    decorators=decorators,
                    is_method=parent_class is not None,
                    class_name=parent_class,
                    file_path=file_path,
                    line_number=node.start_point[0] + 1,
                    line_count=line_count,
                    code=code[:1000],  # Truncate for storage
                    # Metrics
                    is_async=is_async,
                    is_private=is_private,
                    is_static=is_static,
                    has_docstring=has_docstring,
                    has_type_hints=has_type_hints,
                    parameter_count=len(parameters),
                ))

            # Handle classes (to extract methods with class context)
            elif node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    class_name = self._get_text(name_node, source_code)
                    body_node = node.child_by_field_name("body")
                    if body_node:
                        for child in body_node.children:
                            visit_node(child, parent_class=class_name)
                return  # Don't recurse further

            # Recursively visit children
            for child in node.children:
                visit_node(child, parent_class)

        visit_node(tree.root_node)
        return functions

    def extract_calls(self, source_code: str, file_path: str) -> List[CallSite]:
        """Extract function call sites for call graph"""
        tree = self.parser.parse(bytes(source_code, "utf8"))
        calls = []

        def visit_node(node: Node, current_function: Optional[str] = None):
            # Track current function context
            if node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    func_name = self._get_text(name_node, source_code)
                    # Visit function body with this context
                    body_node = node.child_by_field_name("body")
                    if body_node:
                        for child in body_node.children:
                            visit_node(child, current_function=func_name)
                return

            # Extract call expressions
            elif node.type == "call":
                function_node = node.child_by_field_name("function")
                if function_node and current_function:
                    callee = self._get_text(function_node, source_code)
                    # Clean up method calls (e.g., "self.method" -> "method")
                    if '.' in callee:
                        callee = callee.split('.')[-1]

                    calls.append(CallSite(
                        caller=current_function,
                        callee=callee,
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                    ))

            # Recursively visit children
            for child in node.children:
                visit_node(child, current_function)

        visit_node(tree.root_node)
        return calls

    # Helper methods

    def _get_text(self, node: Node, source_code: str) -> str:
        """Extract text content from a node"""
        return source_code[node.start_byte:node.end_byte]

    def _extract_docstring(self, node: Node, source_code: str) -> Optional[str]:
        """Extract docstring from function or class"""
        body_node = node.child_by_field_name("body")
        if body_node and len(body_node.children) > 0:
            first_statement = body_node.children[0]
            if first_statement.type == "expression_statement":
                expr_child = first_statement.children[0] if first_statement.children else None
                if expr_child and expr_child.type == "string":
                    # Remove quotes and unescape
                    docstring = self._get_text(expr_child, source_code)
                    return docstring.strip('"""').strip("'''").strip('"').strip("'").strip()
        return None

    def _extract_decorators(self, node: Node, source_code: str) -> List[str]:
        """Extract decorators from function or class"""
        decorators = []
        # Look for decorated_definition parent
        if node.parent and node.parent.type == "decorated_definition":
            for child in node.parent.children:
                if child.type == "decorator":
                    # Get decorator name (skip @ symbol)
                    dec_text = self._get_text(child, source_code)
                    decorators.append(dec_text.lstrip('@').strip())
        return decorators
