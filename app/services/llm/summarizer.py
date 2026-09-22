"""
Code summarization service using DeepSeek LLM.

This module provides high-level summarization functionality for:
- Individual functions/methods
- Classes
- Files
- Code snippets

It handles batching, rate limiting, and integration with the graph database.
"""

import logging
from typing import List, Dict, Optional, Any
from app.services.llm.client import DeepSeekClient

logger = logging.getLogger(__name__)


class CodeSummarizer:
    """
    High-level code summarization service.

    Uses DeepSeek LLM to generate concise summaries of code elements
    for storage in Neo4j and display in the UI.
    """

    def __init__(self, client: Optional[DeepSeekClient] = None):
        """
        Initialize summarizer.

        Args:
            client: DeepSeek client instance (creates new one if not provided)
        """
        self.client = client or DeepSeekClient()

    def summarize_function(
        self,
        function_name: str,
        code: str,
        language: str = "python",
        file_path: Optional[str] = None,
        class_name: Optional[str] = None,
    ) -> str:
        """
        Summarize a function or method.

        Args:
            function_name: Name of the function
            code: Function source code
            language: Programming language
            file_path: Optional file path for context
            class_name: Optional class name if this is a method

        Returns:
            Summary text
        """
        context_parts = []
        if file_path:
            context_parts.append(f"File: {file_path}")
        if class_name:
            context_parts.append(f"Class: {class_name}")

        context = ", ".join(context_parts) if context_parts else None

        # Limit code length to avoid token limits
        max_code_length = 2000  # characters
        if len(code) > max_code_length:
            code = code[:max_code_length] + "\n... (truncated)"

        return self.client.summarize_code(code, language, context)

    def summarize_class(
        self,
        class_name: str,
        code: str,
        language: str = "python",
        file_path: Optional[str] = None,
        methods: Optional[List[str]] = None,
    ) -> str:
        """
        Summarize a class.

        Args:
            class_name: Name of the class
            code: Class source code
            language: Programming language
            file_path: Optional file path for context
            methods: Optional list of method names

        Returns:
            Summary text
        """
        context_parts = []
        if file_path:
            context_parts.append(f"File: {file_path}")
        if methods:
            context_parts.append(f"Methods: {', '.join(methods[:5])}")  # First 5 methods

        context = ", ".join(context_parts) if context_parts else None

        # Limit code length
        max_code_length = 3000
        if len(code) > max_code_length:
            code = code[:max_code_length] + "\n... (truncated)"

        return self.client.summarize_code(code, language, context)

    def summarize_file(
        self,
        file_path: str,
        language: str,
        structure_summary: Dict[str, Any],
    ) -> str:
        """
        Summarize an entire file based on its structure.

        Args:
            file_path: File path
            language: Programming language
            structure_summary: Dict with counts of imports, classes, functions

        Returns:
            Summary text
        """
        # Create a structured summary prompt
        imports_count = structure_summary.get("imports", 0)
        classes_count = structure_summary.get("classes", 0)
        functions_count = structure_summary.get("functions", 0)

        messages = [
            {
                "role": "system",
                "content": "You are a code analysis expert. Provide concise file summaries."
            },
            {
                "role": "user",
                "content": f"""Summarize this {language} file in 1-2 sentences based on its structure:

File: {file_path}
- {imports_count} imports
- {classes_count} classes
- {functions_count} functions

What is the likely purpose and role of this file in the codebase?"""
            }
        ]

        response = self.client.chat_completion(messages, max_tokens=150)
        return response["content"]

    def summarize_batch(
        self,
        elements: List[Dict[str, Any]],
        max_concurrent: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Summarize multiple code elements in batch.

        Args:
            elements: List of dicts with 'type', 'name', 'code', 'language'
            max_concurrent: Maximum concurrent requests (not implemented yet - sequential for now)

        Returns:
            List of dicts with original data plus 'summary' field
        """
        results = []

        for element in elements:
            element_type = element.get("type")
            name = element.get("name")
            code = element.get("code")
            language = element.get("language", "python")

            try:
                if element_type == "function":
                    summary = self.summarize_function(
                        function_name=name,
                        code=code,
                        language=language,
                        file_path=element.get("file_path"),
                        class_name=element.get("class_name"),
                    )
                elif element_type == "class":
                    summary = self.summarize_class(
                        class_name=name,
                        code=code,
                        language=language,
                        file_path=element.get("file_path"),
                        methods=element.get("methods"),
                    )
                else:
                    # Generic code summary
                    summary = self.client.summarize_code(code, language)

                results.append({
                    **element,
                    "summary": summary,
                })

            except Exception as e:
                logger.warning(f"Error summarizing {element_type} '{name}': {e}")
                results.append({
                    **element,
                    "summary": None,
                    "error": str(e),
                })

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get summarizer statistics"""
        return self.client.get_stats()
