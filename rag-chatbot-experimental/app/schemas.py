from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class DocumentPart:
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class DocumentChunk:
    text: str
    metadata: dict[str, Any]

    @property
    def chunk_id(self) -> str:
        return str(self.metadata.get("chunk_id", ""))


@dataclass(frozen=True)
class EmbeddedChunk:
    chunk: DocumentChunk
    embedding: list[float]


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    metadata: dict[str, Any]
    score: float | None = None


@dataclass(frozen=True)
class QueryRewriteResult:
    original_question: str
    rewritten_question: str
    used: bool
    reason: str


@dataclass(frozen=True)
class RetrievalDiagnostics:
    question_original: str
    question_rewritten: str
    query_rewrite_used: bool
    retrieval_mode: str
    retrieved_chunks_initial: int
    retrieved_chunks_final: int
    confidence: float
    refused: bool = False
    rerank_debug: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class RetrievalResult:
    chunks: list[RetrievedChunk]
    diagnostics: RetrievalDiagnostics


@dataclass(frozen=True)
class IngestionResult:
    documents_loaded: int
    chunks_created: int
    chunks_indexed: int
    failed_files: list[str] = field(default_factory=list)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=20)


class Source(BaseModel):
    file_name: str
    page: str | None = None
    chunk_id: str
    excerpt: str
    score: float | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]


IntentName = Literal[
    "greeting",
    "small_talk",
    "capability_question",
    "rag_question",
    "clarification_needed",
    "out_of_scope",
    "unknown",
]
ProviderName = Literal["mock", "retrieval_only", "openrouter", "ollama"]


class FrontendChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(..., min_length=1)
    mode: str = Field(default="auto")


class FrontendChatResponse(BaseModel):
    conversation_id: str
    answer: str
    intent: IntentName
    used_rag: bool
    sources: list[Source]
    provider: ProviderName
    routing_profile: str | None = None
    routing_score: float | None = None


class ConversationResetRequest(BaseModel):
    conversation_id: str = Field(..., min_length=1)


class ConversationResetResponse(BaseModel):
    status: Literal["reset"]
    conversation_id: str


class HealthResponse(BaseModel):
    status: str
    service: str
