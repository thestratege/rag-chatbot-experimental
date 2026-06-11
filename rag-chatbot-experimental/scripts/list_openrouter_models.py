from __future__ import annotations

import csv
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.openrouter_client import OpenRouterClient, OpenRouterError  # noqa: E402


logger = logging.getLogger(__name__)

RESULTS_DIR = ROOT / "benchmarks" / "results"
CSV_FIELDS = [
    "model_id",
    "name",
    "context_length",
    "provider_family",
    "pricing",
    "supported_parameters",
]


def discover_free_models() -> dict[str, Any]:
    client = OpenRouterClient(settings)
    models = client.list_models()
    free_models = [_normalize_model(model) for model in models if str(model.get("id", "")).endswith(":free")]
    free_models.sort(key=lambda model: model["model_id"])

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "total_models": len(models),
        "free_models_count": len(free_models),
        "free_models": free_models,
    }
    paths = _write_outputs(output, timestamp)
    output["output_paths"] = {key: str(path) for key, path in paths.items()}
    return output


def _normalize_model(model: dict[str, Any]) -> dict[str, Any]:
    model_id = str(model.get("id", ""))
    top_provider = model.get("top_provider") if isinstance(model.get("top_provider"), dict) else {}
    return {
        "model_id": model_id,
        "name": model.get("name", ""),
        "context_length": model.get("context_length") or top_provider.get("context_length"),
        "provider_family": _provider_family(model),
        "pricing": _compact_json(model.get("pricing", {})),
        "supported_parameters": _supported_parameters(model),
        "raw": model,
    }


def _provider_family(model: dict[str, Any]) -> str:
    model_id = str(model.get("id", ""))
    if "/" in model_id:
        return model_id.split("/", 1)[0]
    architecture = model.get("architecture")
    if isinstance(architecture, dict):
        tokenizer = architecture.get("tokenizer")
        if tokenizer:
            return str(tokenizer)
    return ""


def _supported_parameters(model: dict[str, Any]) -> str:
    supported = model.get("supported_parameters")
    if isinstance(supported, list):
        return ", ".join(str(item) for item in supported)
    return _compact_json(supported) if supported else ""


def _compact_json(value: Any) -> str:
    if value in (None, ""):
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _write_outputs(output: dict[str, Any], timestamp: str) -> dict[str, Path]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS_DIR / f"openrouter_free_models_{timestamp}.json"
    csv_path = RESULTS_DIR / f"openrouter_free_models_{timestamp}.csv"

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in output["free_models"]:
            writer.writerow({field: row.get(field) for field in CSV_FIELDS})

    return {"json": json_path, "csv": csv_path}


def _print_table(models: list[dict[str, Any]]) -> None:
    headers = ["model_id", "name", "context_length", "provider_family", "pricing", "supported_parameters"]
    rows = [[_trim(str(model.get(header, "")), 64) for header in headers] for model in models]
    widths = [
        min(64, max(len(header), *(len(row[index]) for row in rows))) if rows else len(header)
        for index, header in enumerate(headers)
    ]
    print(" | ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print(" | ".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(row[index].ljust(widths[index]) for index in range(len(headers))))


def _trim(value: str, max_length: int) -> str:
    return value if len(value) <= max_length else value[: max_length - 3] + "..."


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    try:
        output = discover_free_models()
    except OpenRouterError as exc:
        logger.error("%s", exc)
        return 1

    models = output["free_models"]
    print(f"Modèles gratuits OpenRouter détectés: {len(models)}")
    _print_table(models)
    print(f"JSON: {output['output_paths']['json']}")
    print(f"CSV: {output['output_paths']['csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
