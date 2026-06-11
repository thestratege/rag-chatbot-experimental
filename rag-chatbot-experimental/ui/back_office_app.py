from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402


BENCHMARKS_DIR = ROOT / "benchmarks"
MODELS_PATH = BENCHMARKS_DIR / "openrouter_models.json"
RESULTS_DIR = BENCHMARKS_DIR / "results"
BENCHMARK_SCRIPT = ROOT / "scripts" / "benchmark_openrouter_models.py"
LIST_MODELS_SCRIPT = ROOT / "scripts" / "list_openrouter_models.py"


st.set_page_config(page_title="Back office RAG", layout="wide")
st.title("Back office RAG")


@st.cache_data(show_spinner=False)
def load_models_config() -> list[dict[str, object]]:
    with MODELS_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return list(data.get("models", []))


def latest_result(pattern: str) -> Path | None:
    files = sorted(RESULTS_DIR.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return files[0] if files else None


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


st.header("Benchmark OpenRouter")
st.info(
    "Ce benchmark utilise uniquement les contextes fictifs/anonymisés dans "
    "`benchmarks/rag_test_contexts.json`. Les vrais documents dans `data/documents/` "
    "ne sont jamais envoyés à OpenRouter."
)

models = load_models_config()
enabled_count = sum(1 for model in models if model.get("enabled") is True)

left, right = st.columns(2)
with left:
    st.metric("Modèles configurés", len(models))
with right:
    st.metric("Modèles actifs", enabled_count)

st.subheader("Modèles configurés")
st.dataframe(
    pd.DataFrame(models),
    hide_index=True,
    width="stretch",
)

st.subheader("Lancement")
st.write(f"OpenRouter : `{settings.openrouter_base_url}`")
st.write(f"Limite par run : `{settings.openrouter_max_requests_per_run}` requêtes")
st.write(f"Timeout : `{settings.openrouter_timeout_seconds}` secondes")
st.write(f"Délai configuré : `{settings.openrouter_request_delay_seconds}` secondes")
st.write(f"Délai safe effectif : `{max(35.0, settings.openrouter_request_delay_seconds)}` secondes")
st.write(f"Max safe effectif : `{min(settings.openrouter_max_models_per_run, 3)}` modèle(s), `{min(settings.openrouter_max_questions_per_run, 3)}` question(s)")

if not settings.openrouter_api_key:
    st.warning("OPENROUTER_API_KEY est manquante dans `.env`. Le benchmark ne peut pas appeler OpenRouter.")

actions = st.columns(6)
with actions[0]:
    list_clicked = st.button(
        "Lister les modèles gratuits disponibles",
        width="stretch",
        disabled=not bool(settings.openrouter_api_key),
    )
with actions[1]:
    smoke_clicked = st.button(
        "Lancer smoke test",
        width="stretch",
        disabled=not bool(settings.openrouter_api_key),
    )
with actions[2]:
    safe_clicked = st.button(
        "Lancer benchmark safe",
        width="stretch",
        disabled=not bool(settings.openrouter_api_key),
    )
with actions[3]:
    availability_clicked = st.button(
        "Lancer availability",
        type="primary",
        width="stretch",
        disabled=not bool(settings.openrouter_api_key),
    )
with actions[4]:
    quality_clicked = st.button(
        "Lancer quality depuis availability",
        width="stretch",
        disabled=not bool(settings.openrouter_api_key),
    )
with actions[5]:
    hallucination_clicked = st.button(
        "Lancer anti-hallucination",
        width="stretch",
        disabled=not bool(settings.openrouter_api_key),
    )

command: list[str] | None = None
spinner_message = ""
if list_clicked:
    command = [sys.executable, str(LIST_MODELS_SCRIPT)]
    spinner_message = "Découverte des modèles gratuits OpenRouter..."
elif smoke_clicked:
    command = [sys.executable, str(BENCHMARK_SCRIPT), "--smoke-test"]
    spinner_message = "Smoke test OpenRouter en cours..."
elif safe_clicked:
    command = [sys.executable, str(BENCHMARK_SCRIPT), "--safe"]
    spinner_message = "Benchmark safe OpenRouter en cours..."
elif availability_clicked:
    command = [sys.executable, str(BENCHMARK_SCRIPT), "--availability"]
    spinner_message = "Availability benchmark OpenRouter en cours..."
elif quality_clicked:
    command = [sys.executable, str(BENCHMARK_SCRIPT), "--quality-from-last-availability", "--max-questions", "3"]
    spinner_message = "Quality benchmark OpenRouter en cours..."
elif hallucination_clicked:
    command = [sys.executable, str(BENCHMARK_SCRIPT), "--hallucination-check"]
    spinner_message = "Mini-test anti-hallucination OpenRouter en cours..."

if command:
    with st.spinner(spinner_message):
        completed = run_command(command)
    if completed.returncode == 0:
        st.success("Commande terminée.")
    else:
        st.error("La commande a échoué.")
    if completed.stdout.strip():
        st.code(completed.stdout.strip(), language="text")
    if completed.stderr.strip():
        st.code(completed.stderr.strip(), language="text")
    st.cache_data.clear()

st.subheader("Derniers modèles gratuits détectés")
latest_models_csv = latest_result("openrouter_free_models_*.csv")
if latest_models_csv:
    st.caption(str(latest_models_csv.relative_to(ROOT)))
    st.dataframe(pd.read_csv(latest_models_csv), hide_index=True, width="stretch")
else:
    st.info("Aucune découverte de modèles gratuits disponible pour le moment.")

st.subheader("Dernier benchmark")
latest_benchmark_csv = latest_result("benchmark_openrouter_*.csv")
if latest_benchmark_csv:
    st.caption(str(latest_benchmark_csv.relative_to(ROOT)))
    st.dataframe(pd.read_csv(latest_benchmark_csv), hide_index=True, width="stretch")
else:
    st.info("Aucun CSV de benchmark disponible pour le moment.")

st.subheader("Dernier rapport Markdown")
latest_md = latest_result("benchmark_openrouter_*.md")
if latest_md:
    st.caption(str(latest_md.relative_to(ROOT)))
    st.markdown(latest_md.read_text(encoding="utf-8"))
else:
    st.info("Aucun rapport Markdown disponible pour le moment.")
