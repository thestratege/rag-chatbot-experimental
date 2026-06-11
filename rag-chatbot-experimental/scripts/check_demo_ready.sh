#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
STATUS=0

cd "${PROJECT_ROOT}"

ok() {
  echo "[ok] $1"
}

warn() {
  echo "[attention] $1"
}

fail() {
  echo "[erreur] $1"
  STATUS=1
}

echo "[demo] Vérification rapide de la démo superviseur"

if [ -f ".env" ]; then
  ok ".env existe. Son contenu n'est pas affiché."
elif [ -f ".env.example" ]; then
  warn ".env est absent, mais .env.example existe."
else
  fail ".env et .env.example sont absents."
fi

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if git ls-files --error-unmatch .env >/dev/null 2>&1; then
    fail ".env est suivi par Git. Il ne doit pas être committé."
  else
    ok ".env n'est pas suivi par Git."
  fi
else
  warn "Git n'est pas disponible pour vérifier le statut de .env."
fi

if [ -f "frontend/.env.local" ]; then
  ok "frontend/.env.local existe. Son contenu n'est pas affiché."
else
  warn "frontend/.env.local est absent. Créez-le avec:"
  echo "  cp frontend/.env.local.example frontend/.env.local"
  echo "  VITE_API_BASE_URL=http://127.0.0.1:8010"
fi

if [ -d "frontend" ]; then
  ok "Dossier frontend présent."
else
  fail "Dossier frontend absent."
fi

if [ -f "frontend/package.json" ]; then
  ok "frontend/package.json présent."
else
  fail "frontend/package.json absent."
fi

if [ -d "frontend/node_modules" ]; then
  ok "frontend/node_modules présent."
else
  warn "frontend/node_modules absent. Lancez npm install dans frontend avant la démo."
fi

SAMPLE_DOCS=(
  "data/sample_documents/procedure_acces.txt"
  "data/sample_documents/procedure_mot_de_passe.txt"
  "data/sample_documents/procedure_creation_rapport.txt"
  "data/sample_documents/faq_support.txt"
  "data/sample_documents/politique_utilisation.txt"
)

for doc in "${SAMPLE_DOCS[@]}"; do
  if [ -f "${doc}" ]; then
    ok "Document fictif présent: ${doc}"
  else
    fail "Document fictif absent: ${doc}"
  fi
done

if [ -x ".venv/bin/python" ]; then
  echo "[demo] Lancement des tests Python avec .venv/bin/python -m pytest"
  if .venv/bin/python -m pytest; then
    ok "Tests Python réussis."
  else
    fail "Tests Python en échec."
  fi
else
  warn ".venv/bin/python est absent ou non exécutable. Tests Python non lancés."
fi

if [ "${STATUS}" -eq 0 ]; then
  echo "[demo] Démo prête."
else
  echo "[demo] Vérification terminée avec erreurs."
fi

exit "${STATUS}"
