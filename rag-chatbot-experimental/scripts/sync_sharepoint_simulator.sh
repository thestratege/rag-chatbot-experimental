#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"

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
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://10.100.1.210:11434}"
export OLLAMA_LLM_MODEL="${OLLAMA_LLM_MODEL:-qwen3:14b}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-${OLLAMA_LLM_MODEL}}"
export OLLAMA_EMBEDDING_MODEL="${OLLAMA_EMBEDDING_MODEL:-nomic-embed-text}"

exec "${PYTHON_BIN}" -B scripts/sync_sharepoint_simulator.py
