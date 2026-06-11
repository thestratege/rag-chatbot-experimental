from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.sharepoint_simulator import SharePointSimulator  # noqa: E402


def main() -> int:
    if not settings.sharepoint_simulator_enabled:
        print("Le simulateur SharePoint n'est pas activé. Utilisez scripts/sync_sharepoint_simulator.sh.")
        return 1
    summary = SharePointSimulator(settings).sync()
    data = asdict(summary)
    print(f"Nouveaux documents : {data['added']}")
    print(f"Documents modifiés : {data['modified']}")
    print(f"Documents supprimés : {data['deleted']}")
    print(f"Documents inchangés : {data['unchanged']}")
    print(f"Chunks ajoutés : {data['chunks_added']}")
    print(f"Chunks supprimés : {data['chunks_deleted']}")
    print(f"Erreurs : {data['errors']}")
    return 0 if summary.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
