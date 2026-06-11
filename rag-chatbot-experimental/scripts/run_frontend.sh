#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"

cd "${FRONTEND_DIR}"

if [ ! -f "package.json" ]; then
  echo "[erreur] frontend/package.json est introuvable."
  exit 1
fi

if [ ! -d "node_modules" ]; then
  echo "[erreur] node_modules est introuvable."
  echo "Lancez d'abord:"
  echo "  cd frontend"
  echo "  npm install"
  exit 1
fi

if [ ! -f ".env.local" ]; then
  echo "[attention] frontend/.env.local est absent."
  echo "Pour la démo authentifiée, lancez:"
  echo "  cp frontend/.env.local.example frontend/.env.local"
elif ! rg -q '^VITE_AUTH_DEMO_ENABLED=true$' ".env.local"; then
  echo "[attention] Le champ token de démonstration ne sera pas affiché."
  echo "Ajoutez cette ligne dans frontend/.env.local puis redémarrez Vite:"
  echo "  VITE_AUTH_DEMO_ENABLED=true"
fi

echo "[demo] Lancement du front-end sur http://localhost:5173"

exec npm run dev -- --host 0.0.0.0
