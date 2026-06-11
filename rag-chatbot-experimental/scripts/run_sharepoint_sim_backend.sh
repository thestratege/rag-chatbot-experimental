#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
PORT="${SHAREPOINT_SIM_API_PORT:-8013}"

cd "${PROJECT_ROOT}"

if [ ! -x "${PYTHON_BIN}" ]; then
  echo "[sharepoint-sim] Environnement .venv introuvable."
  exit 1
fi

export SHAREPOINT_SIMULATOR_ENABLED=true
export DOCUMENTS_DIR=data/sharepoint_simulator/documents
export CHROMA_PERSIST_DIR=data/vector_store_sharepoint_sim
export CHROMA_COLLECTION_NAME=sharepoint_simulator_documents
export LLM_PROVIDER=ollama
export OPENROUTER_ENABLED=false
export RAG_AUDIT_LOG_ENABLED=true
export RAG_PERMISSION_FILTERING_ENABLED="${RAG_PERMISSION_FILTERING_ENABLED:-false}"
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://10.100.1.210:11434}"
export OLLAMA_LLM_MODEL="${OLLAMA_LLM_MODEL:-qwen3:14b}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-${OLLAMA_LLM_MODEL}}"
export OLLAMA_EMBEDDING_MODEL="${OLLAMA_EMBEDDING_MODEL:-nomic-embed-text}"
export AUTH_ENABLED="${AUTH_ENABLED:-true}"
export AUTH_PROVIDER="${AUTH_PROVIDER:-mock}"
export DEMO_AUTH_TOKEN="${DEMO_AUTH_TOKEN:-sharepoint-sim-user}"
export DEMO_ADMIN_AUTH_TOKEN="${DEMO_ADMIN_AUTH_TOKEN:-sharepoint-sim-admin}"

echo "[sharepoint-sim] FastAPI: http://127.0.0.1:${PORT}"
echo "[sharepoint-sim] Dashboard: http://localhost:5173/admin?apiBaseUrl=http://127.0.0.1:${PORT}"
echo "[sharepoint-sim] OpenRouter désactivé."

exec "${PYTHON_BIN}" -m uvicorn api.main:app --host 127.0.0.1 --port "${PORT}"
