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
    pipeline = RAGPipeline(settings)
    result = pipeline.ingest_documents()
    print(
        "Ingestion terminée: "
        f"{result.documents_loaded} partie(s), "
        f"{result.chunks_created} chunk(s), "
        f"{result.chunks_indexed} indexé(s)."
    )
    if result.failed_files:
        print("Fichiers ignorés:")
        for failed_file in result.failed_files:
            print(f"- {failed_file}")
    return 0 if result.chunks_indexed > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

