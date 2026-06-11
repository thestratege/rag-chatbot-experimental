from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError:
        return default


def _path_env(name: str, default: str) -> Path:
    raw_value = os.getenv(name, default)
    path = Path(raw_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _list_env(name: str, default: str) -> tuple[str, ...]:
    raw_value = os.getenv(name, default)
    return tuple(item.strip().rstrip("/") for item in raw_value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("ENVIRONMENT", "development").strip().lower()
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock").strip().lower()
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-20b:free")
    ollama_model: str = os.getenv("OLLAMA_MODEL", os.getenv("OLLAMA_LLM_MODEL", "qwen2.5:1.5b-instruct"))
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").rstrip("/")
    allowed_origins: tuple[str, ...] = _list_env(
        "ALLOWED_ORIGINS",
        f"{os.getenv('FRONTEND_ORIGIN', 'http://localhost:5173')},http://127.0.0.1:5173",
    )
    allowed_origins_production: tuple[str, ...] = _list_env(
        "ALLOWED_ORIGINS_PRODUCTION",
        "https://chatbot.example.org,https://tenant.sharepoint.com",
    )
    allowed_frame_ancestors: str = os.getenv(
        "CSP_FRAME_ANCESTORS",
        os.getenv("ALLOWED_FRAME_ANCESTORS", "'self' http://localhost:5173"),
    ).strip()
    public_api_base_url: str = os.getenv("PUBLIC_API_BASE_URL", "http://127.0.0.1:8010").rstrip("/")
    auth_enabled: bool = _bool_env("AUTH_ENABLED", False)
    auth_provider: str = os.getenv("AUTH_PROVIDER", "none").strip().lower()
    demo_auth_token: str = os.getenv("DEMO_AUTH_TOKEN", "").strip()
    demo_admin_auth_token: str = os.getenv("DEMO_ADMIN_AUTH_TOKEN", "").strip()
    entra_tenant_id: str = os.getenv("ENTRA_TENANT_ID", "").strip()
    entra_client_id: str = os.getenv("ENTRA_CLIENT_ID", "").strip()
    entra_audience: str = os.getenv("ENTRA_AUDIENCE", "").strip()
    entra_issuer: str = os.getenv("ENTRA_ISSUER", "").strip()
    auth_required_groups: tuple[str, ...] = _list_env("AUTH_REQUIRED_GROUPS", "")
    conversation_history_limit: int = _int_env("CONVERSATION_HISTORY_LIMIT", 10)
    openrouter_allow_document_context: bool = _bool_env("OPENROUTER_ALLOW_DOCUMENT_CONTEXT", False)
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    ollama_llm_model: str = os.getenv("OLLAMA_MODEL", os.getenv("OLLAMA_LLM_MODEL", "qwen2.5:1.5b-instruct"))
    ollama_embedding_model: str = os.getenv("OLLAMA_EMBEDDING_MODEL", os.getenv("EMBEDDING_MODEL", "nomic-embed-text"))
    vector_db_type: str = os.getenv("VECTOR_DB_TYPE", "chroma")
    chroma_persist_dir: Path = _path_env("CHROMA_PERSIST_DIR", "data/vector_store")
    documents_dir: Path = _path_env("DOCUMENTS_DIR", "data/documents")
    collection_name: str = os.getenv("CHROMA_COLLECTION_NAME", "internal_documents_rag")
    top_k: int = _int_env("TOP_K", 5)
    chunk_size: int = _int_env("CHUNK_SIZE", 1000)
    chunk_overlap: int = _int_env("CHUNK_OVERLAP", 150)
    default_language: str = os.getenv("DEFAULT_LANGUAGE", "fr")
    retrieval_min_score: float = _float_env("RETRIEVAL_MIN_SCORE", 0.15)
    rag_query_rewrite_enabled: bool = _bool_env("RAG_QUERY_REWRITE_ENABLED", False)
    rag_query_rewrite_provider: str = os.getenv("RAG_QUERY_REWRITE_PROVIDER", "ollama").strip().lower()
    rag_query_rewrite_max_tokens: int = _int_env("RAG_QUERY_REWRITE_MAX_TOKENS", 128)
    rag_hybrid_search_enabled: bool = _bool_env("RAG_HYBRID_SEARCH_ENABLED", True)
    rag_vector_top_k: int = _int_env("RAG_VECTOR_TOP_K", 12)
    rag_keyword_top_k: int = _int_env("RAG_KEYWORD_TOP_K", 12)
    rag_final_top_k: int = _int_env("RAG_FINAL_TOP_K", 5)
    rag_keyword_weight: float = _float_env("RAG_KEYWORD_WEIGHT", 0.35)
    rag_vector_weight: float = _float_env("RAG_VECTOR_WEIGHT", 0.65)
    rag_rerank_enabled: bool = _bool_env("RAG_RERANK_ENABLED", True)
    rag_rerank_method: str = os.getenv("RAG_RERANK_METHOD", "heuristic").strip().lower()
    rag_rerank_top_k: int = _int_env("RAG_RERANK_TOP_K", 5)
    rag_confidence_enabled: bool = _bool_env("RAG_CONFIDENCE_ENABLED", True)
    rag_min_confidence: float = _float_env("RAG_MIN_CONFIDENCE", 0.35)
    rag_low_confidence_margin: float = _float_env("RAG_LOW_CONFIDENCE_MARGIN", 0.08)
    rag_diversity_enabled: bool = _bool_env("RAG_DIVERSITY_ENABLED", True)
    rag_max_chunks_per_document: int = _int_env("RAG_MAX_CHUNKS_PER_DOCUMENT", 2)
    rag_permission_filtering_enabled: bool = _bool_env("RAG_PERMISSION_FILTERING_ENABLED", False)
    request_timeout_seconds: int = _int_env("REQUEST_TIMEOUT_SECONDS", 120)
    max_context_chars: int = _int_env("MAX_CONTEXT_CHARS", 12000)
    embedding_batch_size: int = _int_env("EMBEDDING_BATCH_SIZE", 32)
    ollama_num_ctx: int = _int_env("OLLAMA_NUM_CTX", 4096)
    ollama_num_predict: int = _int_env("OLLAMA_NUM_PREDICT", 512)
    ollama_temperature: float = _float_env("OLLAMA_TEMPERATURE", 0.1)
    ollama_think: bool = _bool_env("OLLAMA_THINK", False)
    ollama_keep_alive: str = os.getenv("OLLAMA_KEEP_ALIVE", "10m")
    suppress_httpx_info_logs: bool = _bool_env("SUPPRESS_HTTPX_INFO_LOGS", True)
    sharepoint_simulator_enabled: bool = _bool_env("SHAREPOINT_SIMULATOR_ENABLED", False)
    sharepoint_simulator_state_path: Path = _path_env(
        "SHAREPOINT_SIMULATOR_STATE_PATH",
        "data/sharepoint_simulator/index_state.json",
    )
    sharepoint_simulator_permissions_path: Path = _path_env(
        "SHAREPOINT_SIMULATOR_PERMISSIONS_PATH",
        "data/sharepoint_simulator/permissions.json",
    )
    sharepoint_simulator_log_path: Path = _path_env(
        "SHAREPOINT_SIMULATOR_LOG_PATH",
        "logs/sharepoint_simulator.log",
    )
    rag_audit_log_enabled: bool = _bool_env("RAG_AUDIT_LOG_ENABLED", False)
    rag_audit_log_path: Path = _path_env("RAG_AUDIT_LOG_PATH", "logs/rag_queries.jsonl")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    openrouter_enabled: bool = _bool_env("OPENROUTER_ENABLED", True)
    openrouter_max_requests_per_run: int = _int_env("OPENROUTER_MAX_REQUESTS_PER_RUN", 40)
    openrouter_timeout_seconds: int = _int_env("OPENROUTER_TIMEOUT_SECONDS", 120)
    openrouter_request_delay_seconds: float = _float_env("OPENROUTER_REQUEST_DELAY_SECONDS", 35.0)
    openrouter_max_models_per_run: int = _int_env("OPENROUTER_MAX_MODELS_PER_RUN", 3)
    openrouter_max_questions_per_run: int = _int_env("OPENROUTER_MAX_QUESTIONS_PER_RUN", 3)
    openrouter_retry_on_429: bool = _bool_env("OPENROUTER_RETRY_ON_429", True)
    openrouter_max_retries: int = _int_env("OPENROUTER_MAX_RETRIES", 1)

    @property
    def effective_allowed_origins(self) -> tuple[str, ...]:
        if self.environment == "production":
            return self.allowed_origins_production
        return self.allowed_origins

    def validate(self) -> None:
        if self.environment not in {"development", "demo", "test", "production"}:
            raise ValueError("ENVIRONMENT doit être development, demo, test ou production.")
        if self.llm_provider not in {"mock", "retrieval_only", "openrouter", "ollama"}:
            raise ValueError("LLM_PROVIDER doit être mock, retrieval_only, openrouter ou ollama.")
        if not self.auth_provider:
            raise ValueError("AUTH_PROVIDER ne peut pas être vide.")
        if self.auth_enabled and self.auth_provider == "mock" and (
            not self.demo_auth_token or not self.demo_admin_auth_token
        ):
            raise ValueError(
                "DEMO_AUTH_TOKEN et DEMO_ADMIN_AUTH_TOKEN doivent être définis lorsque AUTH_PROVIDER=mock."
            )
        if self.environment == "production" and self.auth_provider == "mock":
            raise ValueError("AUTH_PROVIDER=mock est réservé aux démonstrations hors production.")
        if not self.effective_allowed_origins:
            raise ValueError("Au moins une origine CORS doit être configurée.")
        if self.environment == "production" and "*" in self.effective_allowed_origins:
            raise ValueError("ALLOWED_ORIGINS_PRODUCTION ne doit pas contenir '*' en production.")
        if self.conversation_history_limit <= 0:
            raise ValueError("CONVERSATION_HISTORY_LIMIT doit être supérieur à 0.")
        if self.chunk_size <= 0:
            raise ValueError("CHUNK_SIZE doit être supérieur à 0.")
        if self.chunk_overlap < 0:
            raise ValueError("CHUNK_OVERLAP ne peut pas être négatif.")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP doit être inférieur à CHUNK_SIZE.")
        if self.top_k <= 0:
            raise ValueError("TOP_K doit être supérieur à 0.")
        if self.rag_query_rewrite_provider != "ollama":
            raise ValueError("RAG_QUERY_REWRITE_PROVIDER doit être ollama dans cette V1 locale.")
        if self.rag_query_rewrite_max_tokens <= 0:
            raise ValueError("RAG_QUERY_REWRITE_MAX_TOKENS doit être supérieur à 0.")
        if min(self.rag_vector_top_k, self.rag_keyword_top_k, self.rag_final_top_k, self.rag_rerank_top_k) <= 0:
            raise ValueError("Les valeurs top_k RAG doivent être supérieures à 0.")
        if self.rag_keyword_weight < 0 or self.rag_vector_weight < 0:
            raise ValueError("Les poids de recherche hybride ne peuvent pas être négatifs.")
        if self.rag_keyword_weight + self.rag_vector_weight <= 0:
            raise ValueError("La somme des poids de recherche hybride doit être supérieure à 0.")
        if self.rag_rerank_method != "heuristic":
            raise ValueError("Seul RAG_RERANK_METHOD=heuristic est supporté dans cette V1.")
        if not 0 <= self.rag_min_confidence <= 1:
            raise ValueError("RAG_MIN_CONFIDENCE doit être compris entre 0 et 1.")
        if self.rag_low_confidence_margin < 0:
            raise ValueError("RAG_LOW_CONFIDENCE_MARGIN ne peut pas être négatif.")
        if self.rag_max_chunks_per_document <= 0:
            raise ValueError("RAG_MAX_CHUNKS_PER_DOCUMENT doit être supérieur à 0.")
        if self.vector_db_type.lower() != "chroma":
            raise ValueError("Seul VECTOR_DB_TYPE=chroma est supporté dans cette V1.")
        if self.embedding_batch_size <= 0:
            raise ValueError("EMBEDDING_BATCH_SIZE doit être supérieur à 0.")
        if self.ollama_num_ctx <= 0:
            raise ValueError("OLLAMA_NUM_CTX doit être supérieur à 0.")
        if self.ollama_num_predict <= 0:
            raise ValueError("OLLAMA_NUM_PREDICT doit être supérieur à 0.")
        if self.openrouter_max_requests_per_run <= 0:
            raise ValueError("OPENROUTER_MAX_REQUESTS_PER_RUN doit être supérieur à 0.")
        if self.openrouter_timeout_seconds <= 0:
            raise ValueError("OPENROUTER_TIMEOUT_SECONDS doit être supérieur à 0.")
        if self.openrouter_request_delay_seconds < 0:
            raise ValueError("OPENROUTER_REQUEST_DELAY_SECONDS ne peut pas être négatif.")
        if self.openrouter_max_models_per_run <= 0:
            raise ValueError("OPENROUTER_MAX_MODELS_PER_RUN doit être supérieur à 0.")
        if self.openrouter_max_questions_per_run <= 0:
            raise ValueError("OPENROUTER_MAX_QUESTIONS_PER_RUN doit être supérieur à 0.")
        if self.openrouter_max_retries < 0:
            raise ValueError("OPENROUTER_MAX_RETRIES ne peut pas être négatif.")


settings = Settings()
settings.validate()
