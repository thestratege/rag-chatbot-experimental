from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import PROJECT_ROOT, settings


def main() -> None:
    source_dir = PROJECT_ROOT / "data" / "sample_documents"
    target_dir = settings.documents_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for source_path in sorted(source_dir.glob("*.txt")):
        target_path = target_dir / source_path.name
        shutil.copy2(source_path, target_path)
        copied += 1
        print(f"Copié: {source_path.relative_to(PROJECT_ROOT)} -> {target_path.relative_to(PROJECT_ROOT)}")

    if copied == 0:
        print("Aucun document fictif trouvé.")
        return
    print(f"{copied} document(s) fictif(s) prêt(s) dans {target_dir.relative_to(PROJECT_ROOT)}.")


if __name__ == "__main__":
    main()
