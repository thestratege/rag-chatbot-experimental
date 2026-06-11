from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.rag_pipeline import RAGPipeline  # noqa: E402


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")


def main() -> int:
    RAGPipeline(settings).reset_vector_store()
    print("Base vectorielle réinitialisée.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

