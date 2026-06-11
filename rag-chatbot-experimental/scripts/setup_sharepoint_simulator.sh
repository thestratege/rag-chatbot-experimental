#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

mkdir -p \
  data/sharepoint_simulator/documents \
  data/sharepoint_simulator/archive \
  data/vector_store_sharepoint_sim \
  logs

touch \
  data/sharepoint_simulator/documents/.gitkeep \
  data/sharepoint_simulator/archive/.gitkeep \
  data/vector_store_sharepoint_sim/.gitkeep \
  logs/.gitkeep

if [ ! -f data/sharepoint_simulator/permissions.json ]; then
  printf '{}\n' > data/sharepoint_simulator/permissions.json
fi

echo "[sharepoint-sim] Environnement prêt."
echo "[sharepoint-sim] Déposez des fichiers .txt, .md ou .pdf texte dans:"
echo "  data/sharepoint_simulator/documents"
echo "[sharepoint-sim] Prochaines commandes:"
echo "  scripts/sync_sharepoint_simulator.sh"
echo "  SHAREPOINT_SIM_API_PORT=8013 scripts/run_sharepoint_sim_backend.sh"
