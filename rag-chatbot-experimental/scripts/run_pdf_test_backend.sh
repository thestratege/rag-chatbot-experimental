#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
PORT="${PDF_TEST_API_PORT:-8010}"

cd "${PROJECT_ROOT}"

if [ ! -x "${PYTHON_BIN}" ]; then
  echo "[pdf-test] Environnement .venv introuvable. Créez-le et installez requirements.txt."
  exit 1
fi

export DOCUMENTS_DIR="data/pdf_test_documents"
export CHROMA_PERSIST_DIR="data/vector_store_pdf_test"
export TOP_K="5"
export CHUNK_SIZE="1000"
export CHUNK_OVERLAP="150"
export MAX_CONTEXT_CHARS="12000"
export OLLAMA_NUM_PREDICT="768"
export LLM_PROVIDER="ollama"
export OPENROUTER_ENABLED="false"

echo "[pdf-test] FastAPI PDF isolé: http://127.0.0.1:${PORT}"
echo "[pdf-test] Documents: ${DOCUMENTS_DIR}"
echo "[pdf-test] Vector store: ${CHROMA_PERSIST_DIR}"

exec "${PYTHON_BIN}" -m uvicorn api.main:app --host 127.0.0.1 --port "${PORT}"
