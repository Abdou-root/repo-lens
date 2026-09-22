"""
LLM API endpoints for code understanding.

Provides endpoints for:
- Code summarization
- Q&A about code
- Code explanation
- Cost tracking
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
import logging
import os

from app.services.llm import (
    DeepSeekClient,
    CodeSummarizer,
    CodeQA,
    CostTracker,
)
from app.auth.dependencies import get_current_user, get_admin_user
from app.db.neo4j_driver import get_driver

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/llm",
    tags=["llm"],
)


# Request/Response models
class SummarizeRequest(BaseModel):
    """Request to summarize code"""
    code: str = Field(..., description="Source code to summarize")
    language: str = Field(default="python", description="Programming language")
    context: Optional[str] = Field(None, description="Additional context about the code")


class SummarizeResponse(BaseModel):
    """Code summarization response"""
    summary: str
    language: str
    tokens_used: int
    cost: float
    cached: bool = False


class QuestionRequest(BaseModel):
    """Q&A question request"""
    question: str = Field(..., description="Question about the code")
    repo_id: Optional[str] = Field(None, description="Repository ID for context")
    code_context: Optional[str] = Field(None, description="Specific code context")
    file_path: Optional[str] = Field(None, description="File path for context")


class QuestionResponse(BaseModel):
    """Q&A answer response"""
    question: str
    answer: str
    sources: List[str] = []
    tokens_used: int
    cost: float
    confidence: Optional[str] = None


class ExplainRequest(BaseModel):
    """Request to explain code"""
    code: str = Field(..., description="Code to explain")
    language: str = Field(default="python", description="Programming language")
    level: str = Field(default="intermediate", description="Explanation level: beginner, intermediate, expert")


class ExplainResponse(BaseModel):
    """Code explanation response"""
    explanation: str
    key_concepts: List[str] = []
    language: str
    tokens_used: int
    cost: float


class CostStatsResponse(BaseModel):
    """Cost tracking statistics"""
    total_requests: int
    total_cost: float
    total_tokens: int
    cached_tokens: int
    cache_hit_rate: float
    cost_by_user: Dict[str, float] = {}
    requests_today: int
    cost_today: float


# Dependency: Get LLM client
def get_llm_client():
    """Get DeepSeek LLM client"""
    from redis import Redis

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="LLM service not configured. Please set DEEPSEEK_API_KEY",
        )

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        redis_client = Redis.from_url(redis_url)
    except Exception:
        redis_client = None

    return DeepSeekClient(
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        redis_client=redis_client,
    )


# Dependency: Get code summarizer
def get_summarizer(client: DeepSeekClient = Depends(get_llm_client)):
    """Get code summarizer service"""
    return CodeSummarizer(client=client)


# Dependency: Get Q&A service
def get_qa_service(client: DeepSeekClient = Depends(get_llm_client)):
    """Get Q&A service"""
    # Q&A retrieves its context from the graph, so it needs the driver.
    try:
        driver = get_driver()
    except Exception as e:
        logger.warning(f"Neo4j unavailable for Q&A retrieval: {e}")
        driver = None
    return CodeQA(client=client, neo4j_driver=driver)


# Endpoints

@router.post("/summarize", response_model=SummarizeResponse)
async def summarize_code(
    request: SummarizeRequest,
    summarizer: CodeSummarizer = Depends(get_summarizer),
    current_user: dict = Depends(get_current_user),
):
    """
    Summarize a code snippet.

    Generates a concise summary of what the code does,
    its purpose, and key functionality.
    """
    user_id = current_user.get("github_id", "anonymous")

    try:
        result = summarizer.summarize_code(
            code=request.code,
            language=request.language,
            context=request.context,
            user_id=user_id,
        )

        return SummarizeResponse(
            summary=result["summary"],
            language=request.language,
            tokens_used=result["tokens_used"],
            cost=result["cost"],
            cached=result.get("cached", False),
        )

    except Exception as e:
        logger.error(f"Summarization failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Summarization failed: {str(e)}",
        )


@router.post("/explain", response_model=ExplainResponse)
async def explain_code(
    request: ExplainRequest,
    summarizer: CodeSummarizer = Depends(get_summarizer),
    current_user: dict = Depends(get_current_user),
):
    """
    Explain code in detail.

    Provides a detailed explanation of how the code works,
    what it does, and why it's structured that way.
    """
    user_id = current_user.get("github_id", "anonymous")

    try:
        result = summarizer.explain_code(
            code=request.code,
            language=request.language,
            level=request.level,
            user_id=user_id,
        )

        return ExplainResponse(
            explanation=result["explanation"],
            key_concepts=result.get("key_concepts", []),
            language=request.language,
            tokens_used=result["tokens_used"],
            cost=result["cost"],
        )

    except Exception as e:
        logger.error(f"Explanation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Explanation failed: {str(e)}",
        )


@router.post("/question", response_model=QuestionResponse)
async def ask_question(
    request: QuestionRequest,
    qa_service: CodeQA = Depends(get_qa_service),
    current_user: dict = Depends(get_current_user),
):
    """
    Ask a question about code.

    Uses RAG (Retrieval-Augmented Generation) to answer
    questions about specific code or repositories.
    """
    user_id = current_user.get("github_id", "anonymous")

    try:
        result = qa_service.answer_question(
            question=request.question,
            repo_id=request.repo_id,
            code_context=request.code_context,
            file_path=request.file_path,
            user_id=user_id,
        )

        return QuestionResponse(
            question=request.question,
            answer=result["answer"],
            sources=result.get("sources", []),
            tokens_used=result["tokens_used"],
            cost=result["cost"],
            confidence=result.get("confidence"),
        )

    except Exception as e:
        logger.error(f"Q&A failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Q&A failed: {str(e)}",
        )


@router.post("/summarize-function")
async def summarize_function(
    code: str,
    function_name: str,
    language: str = "python",
    summarizer: CodeSummarizer = Depends(get_summarizer),
    current_user: dict = Depends(get_current_user),
):
    """
    Summarize a specific function.

    Generates a summary focused on a single function,
    including its purpose, parameters, and return value.
    """
    user_id = current_user.get("github_id", "anonymous")

    try:
        result = summarizer.summarize_function(
            code=code,
            function_name=function_name,
            language=language,
            user_id=user_id,
        )

        return {
            "function_name": function_name,
            "summary": result["summary"],
            "parameters": result.get("parameters", []),
            "return_value": result.get("return_value"),
            "language": language,
            "tokens_used": result["tokens_used"],
            "cost": result["cost"],
        }

    except Exception as e:
        logger.error(f"Function summarization failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Function summarization failed: {str(e)}",
        )


@router.post("/summarize-class")
async def summarize_class(
    code: str,
    class_name: str,
    language: str = "python",
    summarizer: CodeSummarizer = Depends(get_summarizer),
    current_user: dict = Depends(get_current_user),
):
    """
    Summarize a specific class.

    Generates a summary of a class including its purpose,
    methods, and how it should be used.
    """
    user_id = current_user.get("github_id", "anonymous")

    try:
        result = summarizer.summarize_class(
            code=code,
            class_name=class_name,
            language=language,
            user_id=user_id,
        )

        return {
            "class_name": class_name,
            "summary": result["summary"],
            "methods": result.get("methods", []),
            "usage": result.get("usage"),
            "language": language,
            "tokens_used": result["tokens_used"],
            "cost": result["cost"],
        }

    except Exception as e:
        logger.error(f"Class summarization failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Class summarization failed: {str(e)}",
        )


@router.get("/cost/stats", response_model=CostStatsResponse)
async def get_cost_stats(
    current_user: dict = Depends(get_current_user),
):
    """
    Get LLM cost tracking statistics.

    Returns usage and cost information for monitoring and budgeting.
    """
    client = get_llm_client()
    cost_tracker = client.cost_tracker

    stats = cost_tracker.get_stats()

    # Calculate cache hit rate
    total_tokens = stats["total_tokens"]
    cached_tokens = stats["cached_tokens"]
    cache_hit_rate = (cached_tokens / total_tokens * 100) if total_tokens > 0 else 0

    return CostStatsResponse(
        total_requests=stats["total_requests"],
        total_cost=stats["total_cost"],
        total_tokens=total_tokens,
        cached_tokens=cached_tokens,
        cache_hit_rate=cache_hit_rate,
        cost_by_user=stats.get("cost_by_user", {}),
        requests_today=stats.get("requests_today", 0),
        cost_today=stats.get("cost_today", 0),
    )


@router.get("/cost/limits")
async def get_cost_limits(
    current_user: dict = Depends(get_current_user),
):
    """
    Get current cost limits and usage.

    Returns information about rate limits and cost budgets.
    """
    client = get_llm_client()
    cost_tracker = client.cost_tracker

    user_id = current_user.get("github_id", "anonymous")

    # Check current status
    can_request, reason = cost_tracker.can_make_request(user_id=user_id)
    limits_status = cost_tracker.check_cost_limit(user_id=user_id)

    return {
        "can_make_request": can_request,
        "reason": reason,
        "limits": {
            "daily_limit": cost_tracker.limits.daily_limit,
            "monthly_limit": cost_tracker.limits.monthly_limit,
            "per_user_daily_limit": cost_tracker.limits.per_user_daily_limit,
            "requests_per_minute": cost_tracker.limits.requests_per_minute,
        },
        "status": limits_status,
    }


@router.post("/cost/reset")
async def reset_cost_stats(
    current_user: dict = Depends(get_admin_user),
):
    """
    Reset cost tracking statistics.

    Admin endpoint to reset usage tracking.
    Requires admin privileges (ADMIN_GITHUB_IDS env var).
    In development, allows all authenticated users if no admins configured.
    """
    client = get_llm_client()
    cost_tracker = client.cost_tracker

    cost_tracker.reset_all()

    logger.info(f"Cost statistics reset by admin user {current_user.get('github_id')}")

    return {
        "message": "Cost statistics reset successfully",
        "status": "ok",
    }
