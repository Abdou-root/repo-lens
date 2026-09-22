"""
Prompt templates for LLM code understanding tasks.

This module contains carefully crafted prompts for:
- Code summarization
- Code explanation
- Q&A over codebases
- Architectural analysis
"""

from typing import List, Dict

# System prompts for different tasks

SYSTEM_PROMPT_CODE_EXPERT = """You are an expert software engineer and code analyst. You help developers understand codebases by:
- Providing clear, concise explanations
- Focusing on high-level concepts before diving into details
- Using concrete examples when helpful
- Highlighting important patterns and best practices
- Avoiding unnecessary jargon

Always be accurate and honest. If you're not sure about something, say so."""

SYSTEM_PROMPT_SUMMARIZER = """You are a code summarization expert. Your task is to create concise, accurate summaries of code.

Guidelines:
- Focus on WHAT the code does, not HOW (unless specifically asked)
- Use present tense ("This function processes...", not "This function will process...")
- Keep summaries to 2-3 sentences max
- Mention key responsibilities and side effects
- Avoid implementation details unless critical"""

SYSTEM_PROMPT_QA = """You are a codebase Q&A assistant. You help developers understand their codebase by answering questions based on the code context provided.

Guidelines:
- Base your answers on the provided code context
- If the context doesn't contain enough information, say so explicitly
- Cite specific files, functions, or classes when possible
- Provide code examples when helpful
- Be concise but complete"""

# User prompt templates

PROMPT_SUMMARIZE_FUNCTION = """Summarize this {language} function in 2-3 sentences. Focus on its purpose and what it does.

{context}

```{language}
{code}
```"""

PROMPT_SUMMARIZE_CLASS = """Summarize this {language} class in 2-3 sentences. Focus on its responsibility and role.

{context}

```{language}
{code}
```"""

PROMPT_EXPLAIN_CODE = """Explain this {language} code in detail. Include:
1. What it does (high-level purpose)
2. How it works (algorithm/approach)
3. Key components and their interactions
4. Any notable patterns or techniques used

{context}

```{language}
{code}
```"""

PROMPT_EXPLAIN_WITH_QUESTION = """Explain this {language} code, specifically answering this question:

**Question:** {question}

{context}

```{language}
{code}
```"""

PROMPT_QA_WITH_CONTEXT = """Answer the following question about the codebase using the provided code context.

**Question:** {question}

**Relevant Code Context:**

{context}

Provide a clear, detailed answer based on the code shown above. If the context doesn't contain enough information to fully answer the question, explain what information is missing."""

PROMPT_ANALYZE_ARCHITECTURE = """Analyze the architecture of this codebase based on the following structure:

**Files ({file_count}):**
{file_list}

**Key Classes ({class_count}):**
{class_list}

**Dependencies:**
{dependency_info}

Provide a high-level architectural overview covering:
1. Main components and their responsibilities
2. Key patterns used (MVC, layered, microservices, etc.)
3. Technology stack
4. Overall structure and organization"""

PROMPT_FIND_USAGE = """Find and explain how '{target}' is used in this codebase.

**Call Graph:**
{call_graph}

**Related Code:**
{related_code}

Explain:
1. Where '{target}' is defined
2. Where and how it's called/used
3. Its role in the overall system"""

PROMPT_EXPLAIN_FLOW = """Explain the execution flow starting from '{entry_point}'.

**Call Graph:**
{call_graph}

**Code:**
{code}

Describe the step-by-step flow of execution, explaining what happens at each step."""


def format_code_context(
    files: List[str] = None,
    classes: List[str] = None,
    functions: List[str] = None,
    imports: List[str] = None,
) -> str:
    """Format code context for prompts"""
    parts = []

    if files:
        parts.append(f"Files: {', '.join(files)}")
    if classes:
        parts.append(f"Classes: {', '.join(classes)}")
    if functions:
        parts.append(f"Functions: {', '.join(functions)}")
    if imports:
        parts.append(f"Imports: {', '.join(imports)}")

    return "\n".join(parts) if parts else ""


def format_call_graph(edges: List[Dict[str, str]]) -> str:
    """Format call graph edges for prompts"""
    if not edges:
        return "No call graph data available"

    lines = []
    for edge in edges:
        caller = edge.get("source", "unknown")
        callee = edge.get("target", "unknown")
        lines.append(f"  - {caller} → {callee}")

    return "\n".join(lines)


def truncate_code(code: str, max_length: int = 2000) -> str:
    """Truncate code if too long, keeping beginning and end"""
    if len(code) <= max_length:
        return code

    # Keep first and last portions
    portion_size = (max_length - 50) // 2
    beginning = code[:portion_size]
    end = code[-portion_size:]

    return f"{beginning}\n\n... (truncated {len(code) - max_length} characters) ...\n\n{end}"
