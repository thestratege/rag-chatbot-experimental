#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
else
  echo "[info] Aucun environnement .venv détecté. Utilisation du Python courant."
fi

echo "[demo] Lancement FastAPI sur http://127.0.0.1:8010"
echo "[demo] Documentation API: http://127.0.0.1:8010/docs"

exec uvicorn api.main:app --host 127.0.0.1 --port 8010 --reload
