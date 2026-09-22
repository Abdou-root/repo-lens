from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class GraphNode(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "n-1",
                "type": "file",
                "name": "app.js",
                "path": "/app.js",
                "summary": "Main application file",
                "lineCount": 120,
            }
        }
    )

    id: str
    type: str  # 'file' | 'class' | 'function'
    name: str
    path: str
    summary: Optional[str] = None
    code: Optional[str] = None
    lineCount: Optional[int] = None


class GraphEdge(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "e-1",
                "source": "n-1",
                "target": "n-2",
                "type": "imports",
            }
        }
    )

    id: str
    source: str
    target: str
    type: str  # 'imports' | 'calls' | 'inherits'


class Repository(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "repo-abc123",
                "name": "owner/repo",
                "url": "https://github.com/owner/repo",
                "status": "parsing",
                "nodeCount": 10,
                "edgeCount": 12,
                "fileCount": 5,
            }
        }
    )

    id: str
    name: str
    url: str
    status: str = Field("queued", description="queued | parsing | complete | error")
    nodeCount: int = 0
    edgeCount: int = 0
    fileCount: int = 0
    lastAnalyzed: Optional[str] = None
    isDemo: Optional[bool] = False


class Progress(BaseModel):
    current: int
    total: int


class ParseStatus(BaseModel):
    repoId: str
    status: str
    progress: Optional[Progress] = None
    message: Optional[str] = None


class ChatMessage(BaseModel):
    id: str
    role: str  # 'user' | 'assistant'
    content: str
    timestamp: str
    nodeContext: Optional[str] = None


class ChatRequest(BaseModel):
    repoId: Optional[str] = None
    nodeContext: Optional[str] = None
    messages: List[ChatMessage]
    modelOptions: Optional[Dict[str, Any]] = None


# Helper result shapes
class GraphResponse(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]


class ChatDelta(BaseModel):
    type: str  # 'delta' | 'done' | 'error'
    message: Optional[ChatMessage] = None


__all__ = [
    "GraphNode",
    "GraphEdge",
    "Repository",
    "ParseStatus",
    "ChatMessage",
    "ChatRequest",
    "GraphResponse",
    "ChatDelta",
]
