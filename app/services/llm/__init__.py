"""
LLM services for code understanding and Q&A.

This package provides integration with multiple LLM providers for:
- Code summarization
- Code explanation
- RAG-based Q&A over codebases
- Cost tracking and rate limiting

Supported providers:
- OpenRouter (default) - MiMo V2 Flash (free), DeepSeek, Qwen, etc.
- DeepSeek (legacy) - Direct DeepSeek API

Configure via environment:
- LLM_PROVIDER: "openrouter" (default) or "deepseek"
- OPENROUTER_API_KEY: API key for OpenRouter
- OPENROUTER_MODEL: Model to use (default: xiaomi/mimo-v2-flash)
- DEEPSEEK_API_KEY: API key for DeepSeek (legacy)
"""

import os
from typing import Optional, Any, Union

from app.services.llm.client import DeepSeekClient
from app.services.llm.openrouter_client import OpenRouterClient
from app.services.llm.summarizer import CodeSummarizer
from app.services.llm.qa import CodeQA
from app.services.llm.cost_tracker import CostTracker, CostLimit, get_cost_tracker

# Type alias for LLM clients
LLMClient = Union[OpenRouterClient, DeepSeekClient]


def get_llm_client(
    provider: Optional[str] = None,
    redis_client: Optional[Any] = None,
    **kwargs
) -> LLMClient:
    """
    Factory function to get the appropriate LLM client.

    Args:
        provider: "openrouter" or "deepseek" (defaults to LLM_PROVIDER env var or "openrouter")
        redis_client: Redis client for caching (optional)
        **kwargs: Additional arguments passed to the client constructor

    Returns:
        Configured LLM client (OpenRouterClient or DeepSeekClient)

    Example:
        # Use default (OpenRouter with MiMo V2 Flash)
        client = get_llm_client()

        # Use specific provider
        client = get_llm_client(provider="deepseek")

        # With caching
        client = get_llm_client(redis_client=redis)
    """
    provider = provider or os.getenv("LLM_PROVIDER", "openrouter")

    if provider == "openrouter":
        return OpenRouterClient(redis_client=redis_client, **kwargs)
    elif provider == "deepseek":
        return DeepSeekClient(redis_client=redis_client, **kwargs)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}. Use 'openrouter' or 'deepseek'.")


__all__ = [
    # Clients
    'DeepSeekClient',
    'OpenRouterClient',
    'LLMClient',
    # Factory
    'get_llm_client',
    # Services
    'CodeSummarizer',
    'CodeQA',
    # Cost tracking
    'CostTracker',
    'CostLimit',
    'get_cost_tracker',
]
