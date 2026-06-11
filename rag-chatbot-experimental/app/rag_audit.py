from __future__ import annotations

import json
from datetime import UTC, datetime

from app.auth import UserContext
from app.config import Settings, settings
from app.rag_pipeline import NOT_FOUND_ANSWER
from app.schemas import Source


class RAGAuditLogger:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config

    def write(
        self,
        *,
        question: str,
        provider: str,
        sources: list[Source],
        response_time_ms: int,
        user_context: UserContext,
        user_groups: tuple[str, ...],
        answer: str = "",
        error: str | None = None,
        diagnostics: dict[str, object] | None = None,
    ) -> None:
        if not self.config.rag_audit_log_enabled:
            return
        safe_diagnostics = diagnostics or {}
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "question": question[:1000],
            "question_original": str(safe_diagnostics.get("question_original", question))[:1000],
            "question_rewritten": str(safe_diagnostics.get("question_rewritten", question))[:1000],
            "query_rewrite_used": bool(safe_diagnostics.get("query_rewrite_used", False)),
            "provider": provider,
            "model": self.config.ollama_llm_model if provider == "ollama" else provider,
            "retrieval_mode": str(safe_diagnostics.get("retrieval_mode", "unknown")),
            "retrieved_chunks_initial": int(safe_diagnostics.get("retrieved_chunks_initial", len(sources))),
            "retrieved_chunks_final": int(safe_diagnostics.get("retrieved_chunks_final", len(sources))),
            "retrieved_chunks": int(safe_diagnostics.get("retrieved_chunks_final", len(sources))),
            "sources": [source.file_name for source in sources],
            "confidence": float(safe_diagnostics.get("confidence", 0.0)),
            "response_time_ms": response_time_ms,
            "refused": NOT_FOUND_ANSWER.lower() in answer.lower() or not sources,
            "user_id": user_context.user_id,
            "user_groups": list(user_groups),
            "permission_filtering_enabled": self.config.rag_permission_filtering_enabled,
            "error": error[:500] if error else None,
        }
        self.config.rag_audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config.rag_audit_log_path.open("a", encoding="utf-8") as audit_log:
            audit_log.write(json.dumps(event, ensure_ascii=False) + "\n")
