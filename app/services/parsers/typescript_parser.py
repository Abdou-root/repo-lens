"""
TypeScript/JavaScript parser using Tree-sitter for accurate AST traversal.

This parser extracts:
- Import statements (ES6 import/export, CommonJS require)
- Class definitions (including React class components)
- Function definitions (including arrow functions and React hooks)
- TypeScript types (interfaces, types, enums)
- JSX component usage
- Call graph (function invocations)
"""

import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts
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


class TypeScriptParser(LanguageParser):
    """Tree-sitter based TypeScript/JavaScript parser"""

    def __init__(self, is_typescript: bool = True):
        # Initialize Tree-sitter parser with TypeScript or JavaScript language
        # For tree-sitter 0.21.x
        if is_typescript:
            # TypeScript has both typescript and tsx grammars
            TS_LANGUAGE = Language(tsts.language_typescript(), 'typescript')
        else:
            # JavaScript
            JS_LANGUAGE = Language(tsjs.language(), 'javascript')

        self.parser = Parser()
        if is_typescript:
            self.parser.set_language(TS_LANGUAGE)
        else:
            self.parser.set_language(JS_LANGUAGE)

        self.is_typescript = is_typescript
        self._current_class = None  # Track current class context
        self._call_graph = []  # Track calls during traversal

    @property
    def language(self) -> str:
        return "typescript" if self.is_typescript else "javascript"

    def extract_imports(self, source_code: str, file_path: str) -> List[Import]:
        """Extract import statements (ES6 and CommonJS)"""
        tree = self.parser.parse(bytes(source_code, "utf8"))
        imports = []

        def visit_node(node: Node):
            # ES6 import: import X from 'Y', import {A, B} from 'Y'
            if node.type == "import_statement":
                module = None
                names = []

                # Find import source
                for child in node.children:
                    if child.type == "string":
                        module = self._get_text(child, source_code).strip('"').strip("'")
                    elif child.type == "import_clause":
                        # Handle named imports
                        for subchild in child.children:
                            if subchild.type == "named_imports":
                                for import_spec in subchild.children:
                                    if import_spec.type == "import_specifier":
                                        name_node = import_spec.child_by_field_name("name")
                                        if name_node:
                                            names.append(self._get_text(name_node, source_code))
                            elif subchild.type == "identifier":
                                # Default import
                                names.append(self._get_text(subchild, source_code))

                if module:
                    imports.append(Import(
                        module=module,
                        names=names,
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                    ))

            # CommonJS require: const X = require('Y')
            elif node.type == "variable_declarator":
                # Look for require() calls
                init_node = node.child_by_field_name("value")
                if init_node and init_node.type == "call_expression":
                    func_node = init_node.child_by_field_name("function")
                    if func_node and self._get_text(func_node, source_code) == "require":
                        # Get module name from arguments
                        args_node = init_node.child_by_field_name("arguments")
                        if args_node:
                            for child in args_node.children:
                                if child.type == "string":
                                    module = self._get_text(child, source_code).strip('"').strip("'")
                                    # Get variable name
                                    name_node = node.child_by_field_name("name")
                                    var_name = self._get_text(name_node, source_code) if name_node else ""

                                    imports.append(Import(
                                        module=module,
                                        names=[var_name] if var_name else [],
                                        file_path=file_path,
                                        line_number=node.start_point[0] + 1,
                                    ))

            # Recursively visit children
            for child in node.children:
                visit_node(child)

        visit_node(tree.root_node)
        return imports

    def extract_classes(self, source_code: str, file_path: str) -> List[ClassDef]:
        """Extract class definitions (including React class components)"""
        tree = self.parser.parse(bytes(source_code, "utf8"))
        classes = []

        def visit_node(node: Node):
            if node.type == "class_declaration":
                name_node = node.child_by_field_name("name")
                if not name_node:
                    return

                class_name = self._get_text(name_node, source_code)

                # Extract base classes (inheritance)
                base_classes = []
                heritage_node = node.child_by_field_name("heritage")
                if heritage_node:
                    for child in heritage_node.children:
                        if child.type == "extends_clause":
                            for subchild in child.children:
                                if subchild.type == "identifier":
                                    base_classes.append(self._get_text(subchild, source_code))

                # Extract methods
                methods = []
                body_node = node.child_by_field_name("body")
                if body_node:
                    for child in body_node.children:
                        if child.type == "method_definition":
                            method_name_node = child.child_by_field_name("name")
                            if method_name_node:
                                methods.append(self._get_text(method_name_node, source_code))

                # Extract decorators (TypeScript)
                decorators = self._extract_decorators(node, source_code)

                # Get full class code
                code = self._get_text(node, source_code)
                line_count = node.end_point[0] - node.start_point[0] + 1

                # Check if this is a React component
                is_react_component = "Component" in base_classes or "PureComponent" in base_classes

                classes.append(ClassDef(
                    name=class_name,
                    base_classes=base_classes,
                    methods=methods,
                    docstring=None,  # JSDoc comments can be added later
                    decorators=decorators,
                    file_path=file_path,
                    line_number=node.start_point[0] + 1,
                    line_count=line_count,
                    code=code[:1000],  # Truncate for storage
                ))

            # Recursively visit children
            for child in node.children:
                visit_node(child)

        visit_node(tree.root_node)
        return classes

    def extract_functions(self, source_code: str, file_path: str) -> List[FunctionDef]:
        """Extract function and method definitions (including arrow functions and React hooks)"""
        tree = self.parser.parse(bytes(source_code, "utf8"))
        functions = []

        def visit_node(node: Node, parent_class: Optional[str] = None):
            # Regular function declarations
            if node.type == "function_declaration":
                name_node = node.child_by_field_name("name")
                if not name_node:
                    return

                func_name = self._get_text(name_node, source_code)
                self._extract_function_details(node, func_name, parent_class, source_code, file_path, functions)

            # Arrow functions and function expressions assigned to variables
            elif node.type == "variable_declarator":
                name_node = node.child_by_field_name("name")
                value_node = node.child_by_field_name("value")

                if name_node and value_node:
                    func_name = self._get_text(name_node, source_code)

                    # Check if value is an arrow function or function expression
                    if value_node.type in ["arrow_function", "function_expression"]:
                        self._extract_function_details(value_node, func_name, parent_class, source_code, file_path, functions)

                    # Check for React functional components (JSX return)
                    elif value_node.type == "arrow_function":
                        # Check if it returns JSX
                        if self._contains_jsx(value_node, source_code):
                            # Treat as a React component (class-like)
                            pass  # Can be handled in a separate method

            # Method definitions (in classes or object literals)
            elif node.type == "method_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    func_name = self._get_text(name_node, source_code)
                    self._extract_function_details(node, func_name, parent_class, source_code, file_path, functions)

            # Handle classes (to extract methods with class context)
            elif node.type == "class_declaration":
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

    def _extract_function_details(
        self,
        node: Node,
        func_name: str,
        parent_class: Optional[str],
        source_code: str,
        file_path: str,
        functions: List[FunctionDef]
    ):
        """Helper to extract function details"""
        # Extract parameters
        parameters = []
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for child in params_node.children:
                if child.type == "identifier":
                    parameters.append({'name': self._get_text(child, source_code)})
                elif child.type == "required_parameter":
                    param_name_node = child.child_by_field_name("pattern")
                    param_type_node = child.child_by_field_name("type")
                    param_dict = {}
                    if param_name_node:
                        param_dict['name'] = self._get_text(param_name_node, source_code)
                    if param_type_node:
                        param_dict['type'] = self._get_text(param_type_node, source_code)
                    parameters.append(param_dict)
                elif child.type == "optional_parameter":
                    param_name_node = child.child_by_field_name("pattern")
                    param_default_node = child.child_by_field_name("value")
                    param_dict = {}
                    if param_name_node:
                        param_dict['name'] = self._get_text(param_name_node, source_code)
                    if param_default_node:
                        param_dict['default'] = self._get_text(param_default_node, source_code)
                    parameters.append(param_dict)

        # Extract return type (TypeScript)
        return_type = None
        return_type_node = node.child_by_field_name("return_type")
        if return_type_node:
            return_type = self._get_text(return_type_node, source_code)

        # Extract decorators
        decorators = self._extract_decorators(node, source_code)

        # Get full function code
        code = self._get_text(node, source_code)
        line_count = node.end_point[0] - node.start_point[0] + 1

        functions.append(FunctionDef(
            name=func_name,
            parameters=parameters,
            return_type=return_type,
            docstring=None,  # JSDoc can be added later
            decorators=decorators,
            is_method=parent_class is not None,
            class_name=parent_class,
            file_path=file_path,
            line_number=node.start_point[0] + 1,
            line_count=line_count,
            code=code[:1000],  # Truncate for storage
        ))

    def extract_calls(self, source_code: str, file_path: str) -> List[CallSite]:
        """Extract function call sites for call graph"""
        tree = self.parser.parse(bytes(source_code, "utf8"))
        calls = []

        def visit_node(node: Node, current_function: Optional[str] = None):
            # Track current function context
            if node.type in ["function_declaration", "arrow_function", "function_expression", "method_definition"]:
                # Get function name
                func_name = None
                if node.type == "function_declaration":
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        func_name = self._get_text(name_node, source_code)
                elif node.type == "method_definition":
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        func_name = self._get_text(name_node, source_code)

                if func_name:
                    # Visit function body with this context
                    body_node = node.child_by_field_name("body")
                    if body_node:
                        for child in body_node.children:
                            visit_node(child, current_function=func_name)
                return

            # Extract call expressions
            elif node.type == "call_expression":
                function_node = node.child_by_field_name("function")
                if function_node and current_function:
                    callee = self._get_text(function_node, source_code)

                    # Clean up method calls and member expressions
                    if '.' in callee:
                        callee = callee.split('.')[-1]

                    # Handle this.method calls
                    if callee.startswith('this.'):
                        callee = callee.replace('this.', '')

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

    def extract_api_calls(self, source_code: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract API calls (fetch, axios, etc.) for cross-language tracking"""
        tree = self.parser.parse(bytes(source_code, "utf8"))
        api_calls = []

        def visit_node(node: Node, current_function: Optional[str] = None):
            # Track current function/component context
            if node.type in ["function_declaration", "arrow_function", "function_expression", "method_definition"]:
                func_name = None
                if node.type == "function_declaration":
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        func_name = self._get_text(name_node, source_code)
                elif node.type == "method_definition":
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        func_name = self._get_text(name_node, source_code)

                # Update context and continue visiting children (don't return)
                if func_name:
                    current_function = func_name

            # Extract fetch() calls
            if node.type == "call_expression":
                function_node = node.child_by_field_name("function")
                if function_node:
                    func_call_name = self._get_text(function_node, source_code)

                    # Check for fetch(), axios(), or similar
                    if func_call_name in ["fetch", "axios", "axios.get", "axios.post", "axios.put", "axios.delete"]:
                        args_node = node.child_by_field_name("arguments")
                        if args_node:
                            # Find the first string argument (skip parentheses)
                            endpoint = None
                            for child in args_node.children:
                                if child.type == "string":
                                    # Extract string content (remove quotes)
                                    endpoint_text = self._get_text(child, source_code)
                                    endpoint = endpoint_text.strip('"').strip("'")
                                    break

                            if endpoint:
                                # Extract HTTP method
                                method = "GET"  # Default
                                if "post" in func_call_name.lower():
                                    method = "POST"
                                elif "put" in func_call_name.lower():
                                    method = "PUT"
                                elif "delete" in func_call_name.lower():
                                    method = "DELETE"
                                elif func_call_name == "fetch":
                                    # Check for method in options object (look for object child)
                                    for child in args_node.children:
                                        if child.type == "object":
                                            options_text = self._get_text(child, source_code)
                                            if "method:" in options_text or "method :" in options_text:
                                                # Extract method value
                                                import re
                                                method_match = re.search(r"method\s*:\s*['\"](\w+)['\"]", options_text)
                                                if method_match:
                                                    method = method_match.group(1).upper()
                                            break

                                api_calls.append({
                                    "caller": current_function or "anonymous",
                                    "endpoint": endpoint,
                                    "method": method,
                                    "file_path": file_path,
                                    "line_number": node.start_point[0] + 1,
                                })

            # Recursively visit children
            for child in node.children:
                visit_node(child, current_function)

        visit_node(tree.root_node)
        return api_calls

    # Helper methods

    def _get_text(self, node: Node, source_code: str) -> str:
        """Extract text content from a node"""
        return source_code[node.start_byte:node.end_byte]

    def _extract_decorators(self, node: Node, source_code: str) -> List[str]:
        """Extract decorators (TypeScript)"""
        decorators = []
        # TypeScript decorators appear before the node
        if node.parent:
            for sibling in node.parent.children:
                if sibling.type == "decorator":
                    dec_text = self._get_text(sibling, source_code)
                    decorators.append(dec_text.lstrip('@').strip())
        return decorators

    def _contains_jsx(self, node: Node, source_code: str) -> bool:
        """Check if a node contains JSX elements"""
        def check_jsx(n: Node) -> bool:
            if n.type in ["jsx_element", "jsx_self_closing_element"]:
                return True
            for child in n.children:
                if check_jsx(child):
                    return True
            return False

        return check_jsx(node)


class JavaScriptParser(TypeScriptParser):
    """JavaScript parser (convenience wrapper)"""

    def __init__(self):
        super().__init__(is_typescript=False)


class TSXParser(LanguageParser):
    """TSX (TypeScript + JSX) parser"""

    def __init__(self):
        # Use TSX grammar for React TypeScript files
        TSX_LANGUAGE = Language(tsts.language_tsx(), 'tsx')
        self.parser = Parser()
        self.parser.set_language(TSX_LANGUAGE)
        self._ts_parser = TypeScriptParser(is_typescript=True)

    @property
    def language(self) -> str:
        return "tsx"

    def extract_imports(self, source_code: str, file_path: str) -> List[Import]:
        """Delegate to TypeScript parser"""
        return self._ts_parser.extract_imports(source_code, file_path)

    def extract_classes(self, source_code: str, file_path: str) -> List[ClassDef]:
        """Extract classes and React functional components"""
        # First get regular classes
        classes = self._ts_parser.extract_classes(source_code, file_path)

        # Then find functional components (functions that return JSX)
        tree = self.parser.parse(bytes(source_code, "utf8"))

        def visit_node(node: Node):
            # Look for function declarations that return JSX
            if node.type in ["function_declaration", "variable_declarator"]:
                func_name = None

                if node.type == "function_declaration":
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        func_name = self._ts_parser._get_text(name_node, source_code)
                        # Check if it's a React component (starts with uppercase)
                        if func_name and func_name[0].isupper():
                            if self._ts_parser._contains_jsx(node, source_code):
                                # Treat as a component (class-like entity)
                                code = self._ts_parser._get_text(node, source_code)
                                classes.append(ClassDef(
                                    name=func_name,
                                    base_classes=["FunctionalComponent"],
                                    methods=[],
                                    docstring=None,
                                    decorators=[],
                                    file_path=file_path,
                                    line_number=node.start_point[0] + 1,
                                    line_count=node.end_point[0] - node.start_point[0] + 1,
                                    code=code[:1000],
                                ))

                elif node.type == "variable_declarator":
                    name_node = node.child_by_field_name("name")
                    value_node = node.child_by_field_name("value")

                    if name_node and value_node:
                        func_name = self._ts_parser._get_text(name_node, source_code)
                        # Check if it's an arrow function component
                        if func_name and func_name[0].isupper():
                            if value_node.type == "arrow_function" and self._ts_parser._contains_jsx(value_node, source_code):
                                code = self._ts_parser._get_text(node, source_code)
                                classes.append(ClassDef(
                                    name=func_name,
                                    base_classes=["FunctionalComponent"],
                                    methods=[],
                                    docstring=None,
                                    decorators=[],
                                    file_path=file_path,
                                    line_number=node.start_point[0] + 1,
                                    line_count=node.end_point[0] - node.start_point[0] + 1,
                                    code=code[:1000],
                                ))

            # Recursively visit children
            for child in node.children:
                visit_node(child)

        visit_node(tree.root_node)
        return classes

    def extract_functions(self, source_code: str, file_path: str) -> List[FunctionDef]:
        """Delegate to TypeScript parser"""
        return self._ts_parser.extract_functions(source_code, file_path)

    def extract_calls(self, source_code: str, file_path: str) -> List[CallSite]:
        """Delegate to TypeScript parser"""
        return self._ts_parser.extract_calls(source_code, file_path)

    def extract_api_calls(self, source_code: str, file_path: str) -> List[Dict[str, Any]]:
        """Delegate to TypeScript parser"""
        return self._ts_parser.extract_api_calls(source_code, file_path)


class JSXParser(TSXParser):
    """JSX (JavaScript + JSX) parser"""

    def __init__(self):
        # Use JavaScript grammar for JSX files
        JS_LANGUAGE = Language(tsjs.language(), 'javascript')
        self.parser = Parser()
        self.parser.set_language(JS_LANGUAGE)
        self._ts_parser = TypeScriptParser(is_typescript=False)

    @property
    def language(self) -> str:
        return "jsx"
