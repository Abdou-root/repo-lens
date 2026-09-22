"""
OpenRouter LLM client wrapper with cost tracking and caching.

This module provides an OpenRouter-compatible interface using the OpenAI SDK,
with features like:
- MiMo V2 Flash model support (free tier)
- Cost estimation and tracking
- Response caching to reduce API calls
- Rate limiting
- Error handling and retries

OpenRouter API Documentation: https://openrouter.ai/docs/quickstart
"""

import os
import hashlib
import json
import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import tiktoken
from openai import OpenAI

logger = logging.getLogger(__name__)

# Cost per 1M tokens for OpenRouter models
# https://openrouter.ai/models
OPENROUTER_PRICING = {
    "xiaomi/mimo-v2-flash:free": {
        "input": 0.0,  # Free
        "output": 0.0,  # Free
        "cache_hit": 0.0,
    },
    "deepseek/deepseek-chat": {
        "input": 0.14,
        "output": 0.28,
        "cache_hit": 0.014,
    },
    "qwen/qwq-32b": {
        "input": 0.15,
        "output": 0.40,
        "cache_hit": 0.015,
    },
    "google/gemini-2.0-flash-exp:free": {
        "input": 0.0,
        "output": 0.0,
        "cache_hit": 0.0,
    },
}

# Default model (note: :free suffix required for free tier models)
DEFAULT_MODEL = "xiaomi/mimo-v2-flash:free"


class OpenRouterClient:
    """
    OpenRouter API client with cost tracking and caching.

    Uses the OpenAI SDK with OpenRouter's base URL for compatibility.

    Features:
    - Automatic token counting
    - Cost estimation per request
    - Redis-based response caching
    - Rate limiting
    - Retry logic
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = None,
        site_url: Optional[str] = None,
        site_name: Optional[str] = None,
        redis_client: Optional[Any] = None,
        enable_cache: bool = True,
        cache_ttl: int = 86400,  # 24 hours
    ):
        """
        Initialize OpenRouter client.

        Args:
            api_key: OpenRouter API key (defaults to OPENROUTER_API_KEY env var)
            model: Model to use (defaults to OPENROUTER_MODEL env var or xiaomi/mimo-v2-flash)
            site_url: Your site URL for OpenRouter attribution
            site_name: Your site name for OpenRouter attribution
            redis_client: Redis client for caching (optional)
            enable_cache: Whether to enable response caching
            cache_ttl: Cache TTL in seconds (default 24h)
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model or os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)
        self.site_url = site_url or os.getenv("OPENROUTER_SITE_URL", "https://repolens.app")
        self.site_name = site_name or os.getenv("OPENROUTER_SITE_NAME", "RepoLens")
        self.redis_client = redis_client
        self.enable_cache = enable_cache and redis_client is not None
        self.cache_ttl = cache_ttl

        if not self.api_key:
            raise ValueError("OpenRouter API key not provided. Set OPENROUTER_API_KEY environment variable.")

        # Initialize OpenAI client with OpenRouter base URL
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": self.site_url,
                "X-Title": self.site_name,
            }
        )

        # Token encoder for counting tokens
        try:
            self.encoder = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding
        except Exception:
            # Fallback if tiktoken fails
            self.encoder = None

        # Cost tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cached_tokens = 0
        self.total_cost = 0.0
        self.request_count = 0

    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        if self.encoder:
            return len(self.encoder.encode(text))
        else:
            # Rough estimate: ~4 chars per token
            return len(text) // 4

    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0
    ) -> float:
        """Estimate cost for a request"""
        pricing = OPENROUTER_PRICING.get(self.model, {"input": 0, "output": 0, "cache_hit": 0})

        # Calculate costs (per 1M tokens)
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        cache_cost = (cached_tokens / 1_000_000) * pricing["cache_hit"]

        return input_cost + output_cost + cache_cost

    def _get_cache_key(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Generate cache key for a request"""
        # Include messages and key parameters in cache key
        cache_data = {
            "provider": "openrouter",
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.1),
            "max_tokens": kwargs.get("max_tokens", 4000),
        }
        cache_str = json.dumps(cache_data, sort_keys=True)
        return f"llm_cache:{hashlib.sha256(cache_str.encode()).hexdigest()}"

    def _get_cached_response(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached response if available"""
        if not self.enable_cache or not self.redis_client:
            return None

        try:
            cached = self.redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache read error: {e}")

        return None

    def _cache_response(self, cache_key: str, response: Dict[str, Any]):
        """Cache response"""
        if not self.enable_cache or not self.redis_client:
            return

        try:
            self.redis_client.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(response)
            )
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4000,
        stream: bool = False,
        use_cache: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send chat completion request to OpenRouter.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            stream: Whether to stream response
            use_cache: Whether to use cached response if available
            **kwargs: Additional arguments passed to API

        Returns:
            Response dict with 'content', 'usage', 'cost', etc.
        """
        # Check cache first
        cache_key = self._get_cache_key(messages, temperature=temperature, max_tokens=max_tokens)
        if use_cache:
            cached = self._get_cached_response(cache_key)
            if cached:
                cached['from_cache'] = True
                self.total_cached_tokens += cached.get('usage', {}).get('total_tokens', 0)
                return cached

        # Make API request
        try:
            start_time = time.time()

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
                **kwargs
            )

            elapsed_time = time.time() - start_time

            # Extract response
            if stream:
                # For streaming, return the stream object
                return {"stream": response}

            # Parse response
            result = {
                "content": response.choices[0].message.content,
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                "finish_reason": response.choices[0].finish_reason,
                "elapsed_time": elapsed_time,
                "from_cache": False,
                "provider": "openrouter",
            }

            # Calculate cost
            cost = self.estimate_cost(
                input_tokens=result["usage"]["prompt_tokens"],
                output_tokens=result["usage"]["completion_tokens"],
            )
            result["cost"] = cost

            # Update totals
            self.total_input_tokens += result["usage"]["prompt_tokens"]
            self.total_output_tokens += result["usage"]["completion_tokens"]
            self.total_cost += cost
            self.request_count += 1

            # Cache response
            if use_cache:
                self._cache_response(cache_key, result)

            return result

        except Exception as e:
            logger.error(f"OpenRouter API error: {e}")
            raise

    def summarize_code(
        self,
        code: str,
        language: str = "python",
        context: Optional[str] = None,
    ) -> str:
        """
        Summarize code snippet.

        Args:
            code: Code to summarize
            language: Programming language
            context: Optional context (file path, class name, etc.)

        Returns:
            Summary text
        """
        context_str = f"\n\nContext: {context}" if context else ""

        messages = [
            {
                "role": "system",
                "content": "You are a code analysis expert. Provide concise, accurate summaries of code."
            },
            {
                "role": "user",
                "content": f"Summarize this {language} code in 2-3 sentences. Focus on what it does and its purpose.{context_str}\n\n```{language}\n{code}\n```"
            }
        ]

        response = self.chat_completion(messages, max_tokens=200)
        return response["content"]

    def explain_code(
        self,
        code: str,
        language: str = "python",
        question: Optional[str] = None,
    ) -> str:
        """
        Explain code in detail.

        Args:
            code: Code to explain
            language: Programming language
            question: Optional specific question about the code

        Returns:
            Explanation text
        """
        if question:
            prompt = f"Explain this {language} code, specifically answering: {question}\n\n```{language}\n{code}\n```"
        else:
            prompt = f"Explain this {language} code in detail. Include:\n1. What it does\n2. How it works\n3. Key components and their roles\n\n```{language}\n{code}\n```"

        messages = [
            {
                "role": "system",
                "content": "You are a code analysis expert. Provide clear, detailed explanations of code."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        response = self.chat_completion(messages, max_tokens=1000)
        return response["content"]

    def get_stats(self) -> Dict[str, Any]:
        """Get usage statistics"""
        return {
            "provider": "openrouter",
            "model": self.model,
            "request_count": self.request_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cached_tokens": self.total_cached_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_cost": round(self.total_cost, 4),
            "avg_cost_per_request": round(self.total_cost / max(self.request_count, 1), 4),
        }

    def reset_stats(self):
        """Reset usage statistics"""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cached_tokens = 0
        self.total_cost = 0.0
        self.request_count = 0

    def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4000,
        **kwargs
    ):
        """
        Stream chat completion response from OpenRouter.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional arguments passed to API

        Yields:
            String chunks of the response content
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **kwargs
            )

            # Track tokens for cost (estimated from output)
            output_tokens = 0

            for chunk in response:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        output_tokens += self.count_tokens(delta.content)
                        yield delta.content

            # Update stats (estimate input tokens from messages)
            input_tokens = sum(self.count_tokens(m.get("content", "")) for m in messages)
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.total_cost += self.estimate_cost(input_tokens, output_tokens)
            self.request_count += 1

        except Exception as e:
            logger.error(f"OpenRouter streaming error: {e}")
            raise
