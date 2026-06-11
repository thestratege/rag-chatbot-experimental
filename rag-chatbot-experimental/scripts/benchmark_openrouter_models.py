from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings, settings  # noqa: E402
from app.openrouter_client import (  # noqa: E402
    OpenRouterClient,
    OpenRouterError,
    OpenRouterHTTPError,
    OpenRouterResponse,
    OpenRouterTimeoutError,
)


logger = logging.getLogger(__name__)

BENCHMARKS_DIR = ROOT / "benchmarks"
MODELS_PATH = BENCHMARKS_DIR / "openrouter_models.json"
CONTEXTS_PATH = BENCHMARKS_DIR / "rag_test_contexts.json"
QUESTIONS_PATH = BENCHMARKS_DIR / "rag_test_questions.json"
RESULTS_DIR = BENCHMARKS_DIR / "results"

STATUS_SUCCESS = "success"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_MODEL_NOT_FOUND = "model_not_found"
STATUS_API_ERROR = "api_error"
STATUS_TIMEOUT = "timeout"
SKIPPED_MODEL_STATUS = "skipped_model_not_found"
FORBIDDEN_AUTO_ROUTER_MODEL = "openrouter/free"

REFUSAL_ANSWER = "Je ne trouve pas cette information dans les documents fournis."
ABSENT_SOURCES_ANSWER = "Sources :\n- Aucune source pertinente trouvée."
EXPECTED_ABSENT_ANSWER = f"{REFUSAL_ANSWER}\n\n{ABSENT_SOURCES_ANSWER}"
AVAILABILITY_MODEL_IDS = [
    "openai/gpt-oss-20b:free",
    "z-ai/glm-4.5-air:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-nano-9b-v2:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
    "deepseek/deepseek-v4-flash:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct:free",
]
HALLUCINATION_CHECK_MODEL_IDS = [
    "openai/gpt-oss-20b:free",
    "z-ai/glm-4.5-air:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
]
HALLUCINATION_CHECK_QUESTION = "Quelle est la politique de remboursement des frais de déplacement ?"
HALLUCINATION_RESULT_CORRECT_REFUSAL = "correct_refusal"
HALLUCINATION_RESULT_INVENTED_ANSWER = "invented_answer"
HALLUCINATION_RESULT_NON_RELEVANT_SOURCE = "non_relevant_source"
HALLUCINATION_RESULT_NOT_EVALUATED = "not_evaluated"

SYSTEM_PROMPT = """Tu es un assistant RAG documentaire interne.

Tu dois répondre uniquement à partir du CONTEXTE fourni.
Si l’information n’est pas présente dans le CONTEXTE, réponds exactement :
'Je ne trouve pas cette information dans les documents fournis.'
Puis ajoute exactement :
'Sources :
- Aucune source pertinente trouvée.'

Règles obligatoires :

* Réponds en français.
* Ne complète jamais avec tes connaissances générales.
* Ne fais aucune supposition.
* Cite toujours les sources utilisées au format exact :
  Sources :
  - [file_name, page X, chunk_id]
* Si plusieurs sources sont utiles, liste-les à la fin.
* Réponds de façon claire, professionnelle et concise.
* Ne mentionne pas que tu es un modèle IA."""

CSV_FIELDS = [
    "run_id",
    "timestamp",
    "model_id",
    "provider_family",
    "local_equivalent_ollama",
    "question_id",
    "question",
    "status",
    "http_status_code",
    "response_time_seconds",
    "answer",
    "answer_excerpt",
    "error_message",
    "expected_answer_hint",
    "expected_sources",
    "should_refuse_if_absent",
    "answer_length_chars",
    "contains_sources",
    "expected_source_hits",
    "refused_when_absent",
    "exact_absent_refusal",
    "hallucination_check_result",
    "auto_quality_score",
    "auto_rag_quality_score",
    "error",
    "french_quality_score",
    "rag_grounding_score",
    "clarity_score",
    "hallucination_control_score",
    "final_manual_score",
]


class RequestLimiter:
    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = max(0.0, delay_seconds)
        self.last_call_finished_at: float | None = None

    def wait(self) -> None:
        if self.last_call_finished_at is None or self.delay_seconds <= 0:
            return
        elapsed = time.perf_counter() - self.last_call_finished_at
        wait_seconds = self.delay_seconds - elapsed
        if wait_seconds > 0:
            logger.info("Pause quota OpenRouter: %.1fs", wait_seconds)
            time.sleep(wait_seconds)

    def mark_finished(self) -> None:
        self.last_call_finished_at = time.perf_counter()


def _validate_mode_flags(
    *,
    smoke_test: bool,
    safe: bool,
    availability: bool,
    quality_from_last_availability: bool,
    hallucination_check: bool,
) -> None:
    active_modes = [smoke_test, safe, availability, quality_from_last_availability, hallucination_check]
    if sum(1 for active in active_modes if active) > 1:
        raise ValueError(
            "Choisissez un seul mode parmi --smoke-test, --safe, --availability "
            "--quality-from-last-availability et --hallucination-check."
        )


def run_benchmark(
    config: Settings = settings,
    *,
    include_disabled: bool = False,
    max_requests: int | None = None,
    max_models: int | None = None,
    max_questions: int | None = None,
    model_ids: list[str] | None = None,
    request_delay_seconds: float | None = None,
    smoke_test: bool = False,
    safe: bool = False,
    availability: bool = False,
    quality_from_last_availability: bool = False,
    hallucination_check: bool = False,
) -> dict[str, Any]:
    """Run a cautious OpenRouter benchmark against anonymized fictional contexts only."""
    _validate_mode_flags(
        smoke_test=smoke_test,
        safe=safe,
        availability=availability,
        quality_from_last_availability=quality_from_last_availability,
        hallucination_check=hallucination_check,
    )
    if not config.openrouter_enabled:
        raise OpenRouterError("OpenRouter est désactivé avec OPENROUTER_ENABLED=false.")
    if not config.openrouter_api_key:
        raise OpenRouterError("OPENROUTER_API_KEY est manquante dans .env.")

    client = OpenRouterClient(config)
    discovered_models = client.list_models()
    valid_model_ids = {str(model.get("id")) for model in discovered_models if model.get("id")}
    free_models = [model for model in discovered_models if str(model.get("id", "")).endswith(":free")]

    configured_models = _load_all_models()
    if availability:
        model_ids = AVAILABILITY_MODEL_IDS
        include_disabled = True
        max_questions = 1
        max_models = max_models or len(AVAILABILITY_MODEL_IDS)
    elif quality_from_last_availability:
        model_ids = _models_from_last_availability()
        include_disabled = True
        max_questions = max_questions or config.openrouter_max_questions_per_run
    elif hallucination_check:
        model_ids = HALLUCINATION_CHECK_MODEL_IDS
        include_disabled = True
        max_questions = 1
        max_models = max_models or len(HALLUCINATION_CHECK_MODEL_IDS)

    candidate_models = _candidate_models(
        configured_models,
        include_disabled=include_disabled,
        model_ids=model_ids,
    )
    skipped_models = _skipped_models(candidate_models, valid_model_ids)
    valid_candidates = [model for model in candidate_models if str(model.get("model_id")) in valid_model_ids]

    effective_max_models = _effective_max_models(
        config,
        max_models=max_models,
        smoke_test=smoke_test,
        safe=safe,
        availability=availability,
        quality_from_last_availability=quality_from_last_availability,
        hallucination_check=hallucination_check,
        candidate_count=len(candidate_models),
    )
    effective_max_questions = _effective_max_questions(
        config,
        max_questions=max_questions,
        smoke_test=smoke_test,
        safe=safe,
        availability=availability,
        quality_from_last_availability=quality_from_last_availability,
        hallucination_check=hallucination_check,
    )
    effective_delay = _effective_delay(
        config,
        request_delay_seconds=request_delay_seconds,
        safe=safe or availability or quality_from_last_availability or hallucination_check,
    )
    questions = _hallucination_questions() if hallucination_check else _load_questions()[:effective_max_questions]

    selected_models = valid_candidates[:effective_max_models]
    selection_source = "configured_models"
    if not selected_models:
        raise ValueError(
            "Aucun modèle configuré n'a été validé via /models. "
            "Lancez scripts/list_openrouter_models.py puis mettez à jour benchmarks/openrouter_models.json."
        )

    request_limit = max_requests or config.openrouter_max_requests_per_run
    planned_chat_requests = len(selected_models) * len(questions)
    if planned_chat_requests > request_limit:
        raise ValueError(
            f"Benchmark refusé: {planned_chat_requests} requêtes chat prévues, "
            f"limite configurée à {request_limit}."
        )

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    formatted_context = _format_context(_load_contexts())
    contexts = _load_contexts()
    all_source_markers = _source_markers(contexts)
    context_aliases = _source_aliases(contexts)
    results: list[dict[str, Any]] = []

    for model in skipped_models:
        for question in questions:
            results.append(_not_found_result(run_id, model, question))

    limiter = RequestLimiter(effective_delay)
    failed_model_ids: set[str] = set()
    consecutive_rate_limits: defaultdict[str, int] = defaultdict(int)

    logger.info(
        "Benchmark OpenRouter: %s modèle(s), %s question(s), délai %.1fs, source=%s.",
        len(selected_models),
        len(questions),
        effective_delay,
        selection_source,
    )
    for model in selected_models:
        model_id = str(model["model_id"])
        for question in questions:
            if model_id in failed_model_ids:
                results.append(_not_found_result(run_id, model, question))
                continue
            if consecutive_rate_limits[model_id] >= 2:
                results.append(_rate_limited_skipped_result(run_id, model, question))
                continue

            logger.info("Test %s / %s", model_id, question["question_id"])
            result = _evaluate_question(
                client=client,
                limiter=limiter,
                config=config,
                run_id=run_id,
                model=model,
                question=question,
                formatted_context=formatted_context,
                all_source_markers=all_source_markers,
                context_aliases=context_aliases,
            )
            results.append(result)
            if result["status"] == STATUS_MODEL_NOT_FOUND:
                failed_model_ids.add(model_id)
            if result["status"] == STATUS_RATE_LIMITED:
                consecutive_rate_limits[model_id] += 1
            else:
                consecutive_rate_limits[model_id] = 0

    summary = _summarize_results(
        configured_models=configured_models,
        discovered_models=discovered_models,
        selected_models=selected_models,
        skipped_models=skipped_models,
        results=results,
    )
    output = {
        "run": {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "openrouter_base_url": config.openrouter_base_url,
            "mode": _mode_name(
                smoke_test=smoke_test,
                safe=safe,
                availability=availability,
                quality_from_last_availability=quality_from_last_availability,
                hallucination_check=hallucination_check,
            ),
            "selection_source": selection_source,
            "configured_models_count": len(configured_models),
            "valid_configured_models_count": len(valid_candidates),
            "free_models_available_count": len(free_models),
            "models_tested": len(selected_models),
            "questions_tested": len(questions),
            "planned_chat_requests": planned_chat_requests,
            "request_delay_seconds": effective_delay,
            "data_safety": (
                "Ce benchmark utilise uniquement les contextes fictifs/anonymisés "
                "dans benchmarks/rag_test_contexts.json."
            ),
        },
        "system_prompt": SYSTEM_PROMPT,
        "models": selected_models,
        "configured_models": configured_models,
        "skipped_models": skipped_models,
        "questions": questions,
        "results": results,
        "summary": summary,
    }
    paths = _write_outputs(output)
    output["output_paths"] = {key: str(path) for key, path in paths.items()}
    return output


def _evaluate_question(
    *,
    client: OpenRouterClient,
    limiter: RequestLimiter,
    config: Settings,
    run_id: str,
    model: dict[str, Any],
    question: dict[str, Any],
    formatted_context: str,
    all_source_markers: set[str],
    context_aliases: dict[str, set[str]],
) -> dict[str, Any]:
    response, status, http_status_code, response_time, error_message = _chat_with_retry(
        client=client,
        limiter=limiter,
        config=config,
        model_id=str(model["model_id"]),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(formatted_context, str(question["question"]))},
        ],
    )
    answer = response.content if response else ""
    return _result_row(
        run_id=run_id,
        model=model,
        question=question,
        status=status,
        http_status_code=http_status_code,
        response_time=response_time,
        answer=answer,
        error_message=error_message,
        all_source_markers=all_source_markers,
        context_aliases=context_aliases,
    )


def _chat_with_retry(
    *,
    client: OpenRouterClient,
    limiter: RequestLimiter,
    config: Settings,
    model_id: str,
    messages: list[dict[str, str]],
) -> tuple[OpenRouterResponse | None, str, int | None, float | None, str | None]:
    attempt = 0
    while True:
        limiter.wait()
        started = time.perf_counter()
        try:
            response = client.chat_completion(model_id=model_id, messages=messages)
            limiter.mark_finished()
            return response, STATUS_SUCCESS, 200, round(response.response_time_seconds, 3), None
        except OpenRouterTimeoutError as exc:
            limiter.mark_finished()
            return None, STATUS_TIMEOUT, None, round(time.perf_counter() - started, 3), str(exc)
        except OpenRouterHTTPError as exc:
            limiter.mark_finished()
            response_time = round(time.perf_counter() - started, 3)
            if exc.status_code == 429 and config.openrouter_retry_on_429 and attempt < config.openrouter_max_retries:
                wait_seconds = exc.retry_after_seconds or 60.0
                wait_seconds = max(60.0, wait_seconds)
                attempt += 1
                logger.warning(
                    "429 OpenRouter pour %s. Attente %.1fs avant retry %s/%s.",
                    model_id,
                    wait_seconds,
                    attempt,
                    config.openrouter_max_retries,
                )
                time.sleep(wait_seconds)
                continue
            return (
                None,
                _status_from_http_status(exc.status_code),
                exc.status_code,
                response_time,
                str(exc),
            )
        except OpenRouterError as exc:
            limiter.mark_finished()
            return None, STATUS_API_ERROR, None, round(time.perf_counter() - started, 3), str(exc)


def _status_from_http_status(status_code: int) -> str:
    if status_code == 404:
        return STATUS_MODEL_NOT_FOUND
    if status_code == 429:
        return STATUS_RATE_LIMITED
    return STATUS_API_ERROR


def _result_row(
    *,
    run_id: str,
    model: dict[str, Any],
    question: dict[str, Any],
    status: str,
    http_status_code: int | None,
    response_time: float | None,
    answer: str,
    error_message: str | None,
    all_source_markers: set[str],
    context_aliases: dict[str, set[str]],
) -> dict[str, Any]:
    expected_sources = [str(source) for source in question.get("expected_sources", [])]
    expected_aliases = _expected_source_aliases(expected_sources, context_aliases)
    contains_sources = _contains_sources(answer, expected_aliases, all_source_markers)
    expected_source_hits = _expected_source_hits(answer, expected_aliases)
    refused_when_absent = _refused_when_absent(answer, bool(question.get("should_refuse_if_absent")))
    exact_absent_refusal = _exact_absent_refusal(answer)
    hallucination_check_result = _hallucination_check_result(
        answer=answer,
        status=status,
        question_id=str(question.get("question_id", "")),
        all_source_markers=all_source_markers,
    )
    auto_rag_quality_score = _rag_quality_score(
        status=status,
        contains_sources=contains_sources,
        expected_source_hits=expected_source_hits,
        expected_sources=expected_sources,
        refused_when_absent=exact_absent_refusal if question.get("should_refuse_if_absent") else refused_when_absent,
        should_refuse_if_absent=bool(question.get("should_refuse_if_absent")),
    )

    return {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "model_id": model["model_id"],
        "provider_family": model.get("provider_family", ""),
        "local_equivalent_ollama": model.get("local_equivalent_ollama", ""),
        "question_id": question["question_id"],
        "question": question["question"],
        "status": status,
        "http_status_code": http_status_code,
        "response_time_seconds": response_time,
        "answer": answer,
        "answer_excerpt": _answer_excerpt(answer),
        "error_message": error_message,
        "expected_answer_hint": question.get("expected_answer_hint", ""),
        "expected_sources": expected_sources,
        "should_refuse_if_absent": bool(question.get("should_refuse_if_absent")),
        "answer_length_chars": len(answer),
        "contains_sources": contains_sources,
        "expected_source_hits": expected_source_hits,
        "refused_when_absent": refused_when_absent,
        "exact_absent_refusal": exact_absent_refusal,
        "hallucination_check_result": hallucination_check_result,
        "auto_quality_score": _auto_quality_score(
            answer=answer,
            response_time=response_time,
            auto_rag_quality_score=auto_rag_quality_score,
            status=status,
        ),
        "auto_rag_quality_score": auto_rag_quality_score,
        "error": error_message,
        "french_quality_score": None,
        "rag_grounding_score": None,
        "clarity_score": None,
        "hallucination_control_score": None,
        "final_manual_score": None,
    }


def _not_found_result(run_id: str, model: dict[str, Any], question: dict[str, Any]) -> dict[str, Any]:
    return _result_row(
        run_id=run_id,
        model=model,
        question=question,
        status=STATUS_MODEL_NOT_FOUND,
        http_status_code=404,
        response_time=None,
        answer="",
        error_message="Modèle absent de /models; aucune requête chat/completions envoyée.",
        all_source_markers=set(),
        context_aliases={},
    )


def _rate_limited_skipped_result(run_id: str, model: dict[str, Any], question: dict[str, Any]) -> dict[str, Any]:
    return _result_row(
        run_id=run_id,
        model=model,
        question=question,
        status=STATUS_RATE_LIMITED,
        http_status_code=429,
        response_time=None,
        answer="",
        error_message="Modèle déjà limité deux fois dans ce run; requête suivante non envoyée pour préserver le quota.",
        all_source_markers=set(),
        context_aliases={},
    )


def _load_all_models() -> list[dict[str, Any]]:
    data = _load_json(MODELS_PATH)
    models = data.get("models", [])
    if not isinstance(models, list):
        raise ValueError("benchmarks/openrouter_models.json doit contenir une liste 'models'.")
    return [model for model in models if isinstance(model, dict)]


def _load_models(*, include_disabled: bool) -> list[dict[str, Any]]:
    models = _candidate_models(_load_all_models(), include_disabled=include_disabled, model_ids=None)
    if not models:
        raise ValueError("Aucun modèle OpenRouter configuré pour le benchmark.")
    return models


def _candidate_models(
    models: list[dict[str, Any]],
    *,
    include_disabled: bool,
    model_ids: list[str] | None,
) -> list[dict[str, Any]]:
    if model_ids:
        return _models_from_ids(model_ids, models)
    return [
        model
        for model in models
        if (include_disabled or model.get("enabled") is True)
        and _is_allowed_explicit_model(str(model.get("model_id", "")))
    ]


def _models_from_ids(model_ids: list[str], configured_models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    configured_by_id = {str(model.get("model_id")): model for model in configured_models}
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for model_id in model_ids:
        cleaned = model_id.strip()
        if not cleaned or cleaned in seen:
            continue
        if not _is_allowed_explicit_model(cleaned):
            raise ValueError("Le routeur openrouter/free est interdit pour ce benchmark.")
        model = dict(configured_by_id.get(cleaned, _model_config_from_id(cleaned)))
        model["enabled"] = True
        selected.append(model)
        seen.add(cleaned)
    return selected


def _models_from_last_availability() -> list[str]:
    latest = _latest_benchmark_json(mode="availability")
    if latest is None:
        raise ValueError(
            "Aucun availability benchmark trouvé. Lancez d'abord "
            "`python scripts/benchmark_openrouter_models.py --availability`."
        )
    data = _load_json(latest)
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data.get("results", []):
        if isinstance(row, dict):
            by_model[str(row.get("model_id", ""))].append(row)

    selected: list[str] = []
    for model_id, rows in by_model.items():
        if not model_id:
            continue
        successes = _count_status(rows, STATUS_SUCCESS)
        rate_limited = _count_status(rows, STATUS_RATE_LIMITED)
        if successes > 0 and rate_limited <= successes:
            selected.append(model_id)
    if not selected:
        raise ValueError(
            f"Aucun modèle exploitable dans le dernier availability benchmark ({latest.name})."
        )
    return selected


def _latest_benchmark_json(*, mode: str) -> Path | None:
    files = sorted(RESULTS_DIR.glob("benchmark_openrouter_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in files:
        try:
            data = _load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("run", {}).get("mode") == mode:
            return path
    return None


def _is_allowed_explicit_model(model_id: str) -> bool:
    return bool(model_id) and model_id != FORBIDDEN_AUTO_ROUTER_MODEL


def _model_config_from_id(model_id: str) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "provider_family": model_id.split("/", 1)[0] if "/" in model_id else "",
        "enabled": True,
        "expected_strength": "Modèle fourni explicitement en ligne de commande.",
        "local_equivalent_ollama": "",
        "notes": "Ajout temporaire via --models. Vérifié via /models avant tout appel chat.",
    }


def _skipped_models(models: list[dict[str, Any]], valid_model_ids: set[str]) -> list[dict[str, Any]]:
    skipped: list[dict[str, Any]] = []
    for model in models:
        if str(model.get("model_id")) not in valid_model_ids:
            skipped_model = dict(model)
            skipped_model["status"] = SKIPPED_MODEL_STATUS
            skipped_model["reason"] = "Absent de la réponse OpenRouter /models."
            skipped.append(skipped_model)
    return skipped


def _autodiscovered_model_configs(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    for model in sorted(models, key=lambda item: str(item.get("id", ""))):
        model_id = str(model.get("id", ""))
        if not model_id or not _is_allowed_explicit_model(model_id):
            continue
        configs.append(
            {
                "model_id": model_id,
                "provider_family": model_id.split("/", 1)[0] if "/" in model_id else "",
                "enabled": True,
                "expected_strength": "Modèle gratuit découvert automatiquement via /models.",
                "local_equivalent_ollama": "",
                "notes": "Sélection automatique car aucun modèle configuré actif n'a été validé via /models.",
            }
        )
    return configs


def _effective_max_models(
    config: Settings,
    *,
    max_models: int | None,
    smoke_test: bool,
    safe: bool,
    availability: bool,
    quality_from_last_availability: bool,
    hallucination_check: bool,
    candidate_count: int,
) -> int:
    if availability or quality_from_last_availability or hallucination_check:
        return max_models or candidate_count
    if smoke_test:
        return min(max_models or 2, 2)
    if safe:
        return min(max_models or config.openrouter_max_models_per_run, 3)
    return max_models or config.openrouter_max_models_per_run


def _effective_max_questions(
    config: Settings,
    *,
    max_questions: int | None,
    smoke_test: bool,
    safe: bool,
    availability: bool,
    quality_from_last_availability: bool,
    hallucination_check: bool,
) -> int:
    if availability or hallucination_check:
        return 1
    if quality_from_last_availability:
        return min(max_questions or config.openrouter_max_questions_per_run, 5)
    if smoke_test:
        return 1
    if safe:
        return min(max_questions or config.openrouter_max_questions_per_run, 3)
    return max_questions or config.openrouter_max_questions_per_run


def _effective_delay(config: Settings, *, request_delay_seconds: float | None, safe: bool) -> float:
    delay = config.openrouter_request_delay_seconds if request_delay_seconds is None else request_delay_seconds
    return max(35.0, delay) if safe else delay


def _mode_name(
    *,
    smoke_test: bool,
    safe: bool,
    availability: bool,
    quality_from_last_availability: bool,
    hallucination_check: bool,
) -> str:
    if hallucination_check:
        return "hallucination_check"
    if availability:
        return "availability"
    if quality_from_last_availability:
        return "quality_from_last_availability"
    if smoke_test:
        return "smoke_test"
    if safe:
        return "safe"
    return "default"


def _load_contexts() -> list[dict[str, Any]]:
    data = _load_json(CONTEXTS_PATH)
    contexts = data.get("contexts", [])
    if not isinstance(contexts, list) or not contexts:
        raise ValueError("benchmarks/rag_test_contexts.json doit contenir des contextes fictifs.")
    return contexts


def _load_questions() -> list[dict[str, Any]]:
    data = _load_json(QUESTIONS_PATH)
    questions = data.get("questions", [])
    if not isinstance(questions, list) or not questions:
        raise ValueError("benchmarks/rag_test_questions.json doit contenir des questions.")
    return questions


def _hallucination_questions() -> list[dict[str, Any]]:
    return [
        {
            "question_id": "HALLUCINATION_FINAL_ABSENT",
            "question": HALLUCINATION_CHECK_QUESTION,
            "expected_answer_hint": EXPECTED_ABSENT_ANSWER,
            "expected_sources": [],
            "should_refuse_if_absent": True,
        }
    ]


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _format_context(contexts: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for context in contexts:
        page = context.get("page")
        page_label = f"page {page}" if page not in (None, "") else "page non applicable"
        blocks.append(
            "\n".join(
                [
                    f"[{context['source_id']} | {context['file_name']} | {page_label} | chunk {context['chunk_id']}]",
                    str(context["text"]).strip(),
                ]
            )
        )
    return "\n\n---\n\n".join(blocks)


def _user_prompt(formatted_context: str, question: str) -> str:
    return f"""CONTEXTE:
{formatted_context}

QUESTION:
{question}

Réponds en respectant strictement les règles du message système."""


def _source_markers(contexts: list[dict[str, Any]]) -> set[str]:
    markers: set[str] = set()
    for context in contexts:
        markers.add(str(context.get("source_id", "")).lower())
        markers.add(str(context.get("file_name", "")).lower())
        markers.add(str(context.get("chunk_id", "")).lower())
    return {marker for marker in markers if marker}


def _source_aliases(contexts: list[dict[str, Any]]) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    for context in contexts:
        source_id = str(context.get("source_id", ""))
        if not source_id:
            continue
        aliases[source_id] = {
            source_id.lower(),
            str(context.get("file_name", "")).lower(),
            str(context.get("chunk_id", "")).lower(),
        }
    return aliases


def _expected_source_aliases(
    expected_sources: list[str],
    context_aliases: dict[str, set[str]],
) -> list[set[str]]:
    aliases: list[set[str]] = []
    for source in expected_sources:
        source_aliases = context_aliases.get(source, {source.lower()})
        aliases.append({alias for alias in source_aliases if alias})
    return aliases


def _contains_sources(answer: str, expected_aliases: list[set[str]], all_source_markers: set[str]) -> bool:
    if not answer.strip():
        return False
    lowered = answer.lower()
    if any(any(alias in lowered for alias in aliases) for aliases in expected_aliases):
        return True
    if re.search(r"\bsources?\s*:", lowered):
        return True
    if "[file_name" in lowered or "[source" in lowered:
        return True
    if "chunk" in lowered or "page" in lowered:
        return True
    if any(marker in lowered for marker in all_source_markers):
        return True
    return False


def _expected_source_hits(answer: str, expected_aliases: list[set[str]]) -> int:
    lowered = answer.lower()
    return sum(1 for aliases in expected_aliases if any(alias in lowered for alias in aliases))


def _refused_when_absent(answer: str, should_refuse_if_absent: bool) -> bool:
    if not should_refuse_if_absent:
        return False
    return REFUSAL_ANSWER.lower() in " ".join(answer.split()).lower()


def _exact_absent_refusal(answer: str) -> bool:
    normalized = _normalize_absent_refusal_text(answer)
    pattern = (
        r"^je ne trouve pas cette information dans les documents fournis\.?\s+"
        r"sources?\s*:\s*-?\s*aucune source pertinente trouvée\.?$"
    )
    return bool(re.match(pattern, normalized))


def _normalize_answer(answer: str) -> str:
    lines = [line.strip() for line in answer.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")]
    normalized_lines: list[str] = []
    previous_blank = False
    for line in lines:
        is_blank = line == ""
        if is_blank and previous_blank:
            continue
        normalized_lines.append(line)
        previous_blank = is_blank
    return "\n".join(normalized_lines).strip()


def _normalize_absent_refusal_text(answer: str) -> str:
    normalized = answer.replace("\u00a0", " ")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]*\n[ \t]*", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip().lower()


def _hallucination_check_result(
    *,
    answer: str,
    status: str,
    question_id: str,
    all_source_markers: set[str],
) -> str:
    if question_id != "HALLUCINATION_FINAL_ABSENT" or status != STATUS_SUCCESS:
        return HALLUCINATION_RESULT_NOT_EVALUATED
    if _exact_absent_refusal(answer):
        return HALLUCINATION_RESULT_CORRECT_REFUSAL
    if _cites_non_relevant_source(answer, all_source_markers):
        return HALLUCINATION_RESULT_NON_RELEVANT_SOURCE
    return HALLUCINATION_RESULT_INVENTED_ANSWER


def _cites_non_relevant_source(answer: str, all_source_markers: set[str]) -> bool:
    lowered = answer.lower()
    if "aucune source pertinente trouvée" in lowered and not any(marker in lowered for marker in all_source_markers):
        return False
    if any(marker in lowered for marker in all_source_markers):
        return True
    if re.search(r"\bsources?\s*:\s*-?\s*\[", lowered):
        return True
    if "page" in lowered or "chunk" in lowered:
        return True
    return False


def _rag_quality_score(
    *,
    status: str,
    contains_sources: bool,
    expected_source_hits: int,
    expected_sources: list[str],
    refused_when_absent: bool,
    should_refuse_if_absent: bool,
) -> float:
    if status != STATUS_SUCCESS:
        return 0.0
    if should_refuse_if_absent:
        return 5.0 if refused_when_absent else 0.0

    score = 0.0
    if contains_sources:
        score += 2.0
    if expected_sources:
        score += 3.0 * (expected_source_hits / len(expected_sources))
    return round(min(score, 5.0), 2)


def _auto_quality_score(
    *,
    answer: str,
    response_time: float | None,
    auto_rag_quality_score: float,
    status: str,
) -> float:
    if status != STATUS_SUCCESS:
        return 0.0
    score = auto_rag_quality_score
    if answer.strip():
        score += 1.5
    if 20 <= len(answer) <= 2000:
        score += 1.0
    if response_time is not None:
        if response_time <= 8:
            score += 2.5
        elif response_time <= 20:
            score += 1.5
        else:
            score += 0.5
    return round(min(score, 10.0), 2)


def _summarize_results(
    *,
    configured_models: list[dict[str, Any]],
    discovered_models: list[dict[str, Any]],
    selected_models: list[dict[str, Any]],
    skipped_models: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    selected_meta = {model["model_id"]: model for model in selected_models}
    for result in results:
        by_model[str(result["model_id"])].append(result)

    model_summaries: list[dict[str, Any]] = []
    for model_id, rows in by_model.items():
        successes = [row for row in rows if row["status"] == STATUS_SUCCESS]
        timed = [row["response_time_seconds"] for row in successes if row["response_time_seconds"] is not None]
        absent_rows = [row for row in successes if row["should_refuse_if_absent"]]
        non_absent_rows = [row for row in successes if not row["should_refuse_if_absent"]]
        source_rows = [row for row in non_absent_rows if row["contains_sources"]]
        refusal_rows = [row for row in absent_rows if row["refused_when_absent"]]
        exact_refusal_rows = [row for row in absent_rows if row.get("exact_absent_refusal")]
        meta = selected_meta.get(model_id, _configured_model_meta(configured_models, model_id))
        model_summaries.append(
            {
                "model_id": model_id,
                "provider_family": meta.get("provider_family", ""),
                "local_equivalent_ollama": meta.get("local_equivalent_ollama", ""),
                "requests": len(rows),
                "successes": len(successes),
                "rate_limited": _count_status(rows, STATUS_RATE_LIMITED),
                "model_not_found": _count_status(rows, STATUS_MODEL_NOT_FOUND),
                "api_errors": _count_status(rows, STATUS_API_ERROR),
                "timeouts": _count_status(rows, STATUS_TIMEOUT),
                "avg_response_time_seconds": round(mean(timed), 3) if timed else None,
                "avg_auto_quality_score": _safe_mean(row["auto_quality_score"] for row in rows),
                "avg_auto_rag_quality_score": _safe_mean(row["auto_rag_quality_score"] for row in rows),
                "source_presence_rate": round(len(source_rows) / len(non_absent_rows), 3) if non_absent_rows else None,
                "refusal_success_rate": round(len(refusal_rows) / len(absent_rows), 3) if absent_rows else None,
                "exact_refusal_success_rate": round(len(exact_refusal_rows) / len(absent_rows), 3) if absent_rows else None,
                "hallucination_correct_refusals": _count_hallucination(rows, HALLUCINATION_RESULT_CORRECT_REFUSAL),
                "hallucination_invented_answers": _count_hallucination(rows, HALLUCINATION_RESULT_INVENTED_ANSWER),
                "hallucination_non_relevant_sources": _count_hallucination(rows, HALLUCINATION_RESULT_NON_RELEVANT_SOURCE),
            }
        )

    provisional_ranking = sorted(
        [row for row in model_summaries if row["successes"] >= 3],
        key=lambda row: (
            -(row["avg_auto_quality_score"] or 0),
            row["avg_response_time_seconds"] if row["avg_response_time_seconds"] is not None else 9999,
        ),
    )
    speed_ranking = sorted(
        [row for row in model_summaries if row["successes"] > 0],
        key=lambda row: row["avg_response_time_seconds"] if row["avg_response_time_seconds"] is not None else 9999,
    )
    rag_ranking = sorted(
        [row for row in model_summaries if row["successes"] > 0],
        key=lambda row: (
            -(row["avg_auto_rag_quality_score"] or 0),
            row["avg_response_time_seconds"] if row["avg_response_time_seconds"] is not None else 9999,
        ),
    )

    return {
        "configured_models_count": len(configured_models),
        "available_configured_models_count": len(
            {
                model["model_id"]
                for model in configured_models
                if any(str(discovered.get("id")) == str(model.get("model_id")) for discovered in discovered_models)
            }
        ),
        "models_tested_count": len(selected_models),
        "success_count": _count_status(results, STATUS_SUCCESS),
        "not_found_count": _count_status(results, STATUS_MODEL_NOT_FOUND),
        "rate_limited_count": _count_status(results, STATUS_RATE_LIMITED),
        "api_error_count": _count_status(results, STATUS_API_ERROR),
        "timeout_count": _count_status(results, STATUS_TIMEOUT),
        "error_count": len([row for row in results if row["status"] != STATUS_SUCCESS]),
        "skipped_models": skipped_models,
        "models": model_summaries,
        "provisional_ranking": provisional_ranking,
        "speed_ranking": speed_ranking,
        "rag_ranking": rag_ranking,
        "recommended_cloud_model": provisional_ranking[0] if provisional_ranking else None,
        "recommended_local_ollama_candidate": _recommend_local_candidate(provisional_ranking),
    }


def _configured_model_meta(models: list[dict[str, Any]], model_id: str) -> dict[str, Any]:
    for model in models:
        if str(model.get("model_id")) == model_id:
            return model
    return {}


def _count_status(rows: list[dict[str, Any]], status: str) -> int:
    return sum(1 for row in rows if row.get("status") == status)


def _count_hallucination(rows: list[dict[str, Any]], result: str) -> int:
    return sum(1 for row in rows if row.get("hallucination_check_result") == result)


def _safe_mean(values: Any) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    return round(mean(numbers), 3) if numbers else None


def _recommend_local_candidate(ranking: list[dict[str, Any]]) -> dict[str, Any] | None:
    usable = [row for row in ranking if row["successes"] >= 3]
    local_friendly = [
        row
        for row in usable
        if "70b" not in str(row.get("local_equivalent_ollama", "")).lower()
        and "très équipée" not in str(row.get("local_equivalent_ollama", "")).lower()
    ]
    return (local_friendly or usable)[0] if usable else None


def _write_outputs(output: dict[str, Any]) -> dict[str, Path]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = str(output["run"]["run_id"])
    json_path = RESULTS_DIR / f"benchmark_openrouter_{run_id}.json"
    csv_path = RESULTS_DIR / f"benchmark_openrouter_{run_id}.csv"
    md_path = RESULTS_DIR / f"benchmark_openrouter_{run_id}.md"

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in output["results"]:
            csv_row = {field: row.get(field) for field in CSV_FIELDS}
            csv_row["expected_sources"] = ", ".join(row.get("expected_sources", []))
            writer.writerow(csv_row)

    md_path.write_text(_markdown_report(output), encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "markdown": md_path}


def _markdown_report(output: dict[str, Any]) -> str:
    run = output["run"]
    summary = output["summary"]
    mode = run["mode"]
    lines = [
        "# Rapport Benchmark OpenRouter",
        "",
        "## Résumé exécutif",
        "",
        f"- Run : `{run['run_id']}`",
        f"- Mode : `{run['mode']}`",
        f"- Modèles configurés : {summary['configured_models_count']}",
        f"- Modèles configurés réellement disponibles via `/models` : {summary['available_configured_models_count']}",
        f"- Modèles testés : {summary['models_tested_count']}",
        f"- Succès HTTP 200 : {summary['success_count']}",
        f"- Erreurs 404 / modèle introuvable : {summary['not_found_count']}",
        f"- Requêtes limitées 429 : {summary['rate_limited_count']}",
        f"- Autres erreurs API : {summary['api_error_count']}",
        f"- Timeouts : {summary['timeout_count']}",
        f"- Délai entre requêtes : {run['request_delay_seconds']}s",
        "",
        _best_model_sentence(summary),
        "",
        "## Mini-test anti-hallucination",
        "",
        _hallucination_check_table(output["results"]) if mode == "hallucination_check" else "Non applicable pour ce mode.",
        "",
        "## Meilleur modèle final provisoire",
        "",
        _hallucination_final_recommendation(summary) if mode == "hallucination_check" else "Non applicable pour ce mode.",
        "",
        "## Disponibilité du modèle",
        "",
        _availability_table(summary["models"]),
        "",
        "## Modèles ignorés car introuvables",
        "",
        _skipped_models_table(summary["skipped_models"]),
        "",
        "## Requêtes limitées par rate limit",
        "",
        _rate_limited_table(output["results"]),
        "",
        "## Qualité RAG",
        "",
        _quality_table(summary["models"]),
        "",
        "## Classement provisoire",
        "",
        "Seuls les modèles ayant au moins 3 réponses réussies sont classés.",
        "",
        _ranking_table(summary["provisional_ranking"]),
        "",
        "## Extraits de réponses",
        "",
        _answer_excerpts_table(output["results"]),
        "",
        "## Analyse pour notre projet RAG",
        "",
        _rag_project_analysis(summary),
        "",
        "## Recommandation provisoire",
        "",
        _recommendations_block(summary),
        "",
        "## Résultats détaillés",
        "",
        _detailed_results_table(output["results"]),
        "",
        "## Champs de notation manuelle",
        "",
        "Les colonnes suivantes restent à remplir après revue humaine : "
        "`french_quality_score`, `rag_grounding_score`, `clarity_score`, "
        "`hallucination_control_score`, `final_manual_score`.",
        "",
        "## Limites du benchmark",
        "",
        "- Les modèles gratuits OpenRouter sont soumis à des limites de débit et à la disponibilité des fournisseurs upstream.",
        "- Certains slugs configurés peuvent être invalides ou disparaître ; ils doivent être vérifiés via `/models` avant un run.",
        f"- Mode du rapport : `{mode}`. La phase availability mesure surtout la disponibilité, pas la qualité RAG.",
        "- Le benchmark reste incomplet tant qu'une phase quality n'a pas été lancée sur les modèles disponibles.",
        "- Les résultats automatiques ne remplacent pas une revue humaine de la qualité du français et du grounding RAG.",
        "- N'envoyez jamais de documents sensibles vers OpenRouter ; ce benchmark utilise seulement des contextes fictifs/anonymisés.",
        "",
    ]
    return "\n".join(lines)


def _best_model_sentence(summary: dict[str, Any]) -> str:
    best = summary.get("recommended_cloud_model")
    if not best:
        return "- Meilleur modèle provisoire : données insuffisantes."
    return (
        "- Meilleur modèle provisoire : "
        f"`{best['model_id']}` avec {best['successes']} réponses réussies, "
        f"score auto moyen {_value(best['avg_auto_quality_score'])}."
    )


def _successful_models_table(rows: list[dict[str, Any]]) -> str:
    successful = [row for row in rows if row["successes"] > 0]
    if not successful:
        return "Aucun modèle n'a produit de réponse HTTP 200 exploitable."
    return _model_table(successful)


def _availability_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Aucun modèle testé."
    lines = [
        "| Modèle | Statut | Succès | 429 | Erreurs | Temps moyen |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        errors = row["model_not_found"] + row["api_errors"] + row["timeouts"]
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["model_id"]),
                    _model_status_label(row),
                    str(row["successes"]),
                    str(row["rate_limited"]),
                    str(errors),
                    _seconds(row["avg_response_time_seconds"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _quality_table(rows: list[dict[str, Any]]) -> str:
    successful = [row for row in rows if row["successes"] > 0]
    if not successful:
        return "Aucune réponse HTTP 200 disponible pour évaluer la qualité RAG."
    lines = [
        "| Modèle | Sources | Refus hallucination | Qualité RAG provisoire | Français | Clarté |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in successful:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["model_id"]),
                    _rate(row["source_presence_rate"]),
                    _rate(row["refusal_success_rate"]),
                    _value(row["avg_auto_rag_quality_score"]),
                    "revue humaine requise",
                    "revue humaine requise",
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _skipped_models_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Aucun modèle configuré actif n'a été ignoré comme introuvable via `/models`."
    lines = [
        "| Modèle | Statut | Raison |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('model_id')} | {row.get('status', SKIPPED_MODEL_STATUS)} | {_clean_markdown_cell(row.get('reason', ''))} |"
        )
    return "\n".join(lines)


def _rate_limited_table(results: list[dict[str, Any]]) -> str:
    rows = [row for row in results if row["status"] == STATUS_RATE_LIMITED]
    if not rows:
        return "Aucune requête n'a terminé en 429 dans ce run."
    lines = [
        "| Modèle | Question | HTTP | Message |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['model_id']} | {row['question_id']} | {row['http_status_code']} | "
            f"{_clean_markdown_cell(row.get('error_message') or '')} |"
        )
    return "\n".join(lines)


def _hallucination_check_table(results: list[dict[str, Any]]) -> str:
    if not results:
        return "Aucun résultat anti-hallucination disponible."
    lines = [
        "| Modèle | HTTP | Statut | Refus exact | Invente | Source non pertinente | Temps | Extrait |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in results:
        check = row.get("hallucination_check_result")
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["model_id"]),
                    _value(row["http_status_code"]),
                    str(row["status"]),
                    "oui" if check == HALLUCINATION_RESULT_CORRECT_REFUSAL else "non",
                    "oui" if check == HALLUCINATION_RESULT_INVENTED_ANSWER else "non",
                    "oui" if check == HALLUCINATION_RESULT_NON_RELEVANT_SOURCE else "non",
                    _seconds(row["response_time_seconds"]),
                    _clean_markdown_cell(row.get("answer_excerpt") or row.get("error_message") or ""),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _hallucination_final_recommendation(summary: dict[str, Any]) -> str:
    rows = summary.get("models", [])
    correct = [
        row
        for row in rows
        if row.get("hallucination_correct_refusals", 0) > 0 and row.get("successes", 0) > 0
    ]
    invented = [row["model_id"] for row in rows if row.get("hallucination_invented_answers", 0) > 0]
    non_relevant = [row["model_id"] for row in rows if row.get("hallucination_non_relevant_sources", 0) > 0]
    unavailable = [row["model_id"] for row in rows if row.get("successes", 0) == 0]

    if correct:
        correct.sort(key=lambda row: row["avg_response_time_seconds"] if row["avg_response_time_seconds"] is not None else 9999)
        best = correct[0]
        lines = [
            f"- Meilleur modèle final provisoire pour le benchmark cloud gratuit : `{best['model_id']}`.",
            f"- Modèle à tester ensuite localement avec Ollama : `{best.get('local_equivalent_ollama', '')}`.",
        ]
    else:
        lines = [
            "- Aucun modèle n'a réussi le refus exact. Ne pas déclarer de gagnant final.",
        ]

    if invented:
        lines.append("- Modèles qui inventent : " + ", ".join(f"`{model}`" for model in invented) + ".")
    if non_relevant:
        lines.append(
            "- Modèles qui citent une source non pertinente : "
            + ", ".join(f"`{model}`" for model in non_relevant)
            + "."
        )
    if unavailable:
        lines.append(
            "- Modèles non évaluables dans ce run : "
            + ", ".join(f"`{model}`" for model in unavailable)
            + "."
        )
    return "\n".join(lines)


def _ranking_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Aucun modèle n'a au moins 3 réponses réussies ; classement provisoire indisponible."
    return _model_table(rows)


def _model_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Rang | Modèle | Statut | Succès | 429 | 404 | Temps moyen | Sources | Refus absent | Qualité RAG provisoire | Équivalent Ollama |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, row in enumerate(rows, start=1):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(index),
                    str(row["model_id"]),
                    _model_status_label(row),
                    str(row["successes"]),
                    str(row["rate_limited"]),
                    str(row["model_not_found"]),
                    _seconds(row["avg_response_time_seconds"]),
                    _rate(row["source_presence_rate"]),
                    _rate(row["refusal_success_rate"]),
                    _value(row["avg_auto_rag_quality_score"]),
                    str(row.get("local_equivalent_ollama", "")),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _rag_project_analysis(summary: dict[str, Any]) -> str:
    best = summary.get("recommended_cloud_model")
    if not best:
        return (
            "- Qualité de réponse : données insuffisantes.\n"
            "- Respect du contexte : données insuffisantes.\n"
            "- Refus d'hallucination : non concluant sans réponses réussies sur les questions d'absence.\n"
            "- Qualité du français : à noter manuellement dans le CSV.\n"
            "- Présence des sources : non concluant.\n"
            "- Vitesse : non concluant.\n"
            "- Pertinence Ollama : aucun candidat local à recommander pour l'instant."
        )
    return (
        f"- Qualité de réponse : `{best['model_id']}` est le meilleur candidat provisoire selon la note automatique.\n"
        f"- Respect du contexte : score RAG moyen {_value(best['avg_auto_rag_quality_score'])}/5 sur les réponses obtenues.\n"
        f"- Refus d'hallucination : taux de refus attendu {_value(best['refusal_success_rate'])} quand les questions d'absence ont réussi.\n"
        "- Qualité du français : à évaluer manuellement dans le CSV, car la note automatique ne juge pas le style.\n"
        f"- Présence des sources : taux {_value(best['source_presence_rate'])} sur les questions non absentes réussies.\n"
        f"- Vitesse : temps moyen {_seconds(best['avg_response_time_seconds'])}.\n"
        f"- Pertinence Ollama : comparer avec `{best.get('local_equivalent_ollama', '')}` si un équivalent local raisonnable existe."
    )


def _recommendations_block(summary: dict[str, Any]) -> str:
    best = summary.get("recommended_cloud_model")
    local = summary.get("recommended_local_ollama_candidate")
    exploitable = sorted(
        [row for row in summary.get("models", []) if row["successes"] > 0],
        key=lambda row: (
            -(row["successes"] or 0),
            row["rate_limited"],
            row["avg_response_time_seconds"] if row["avg_response_time_seconds"] is not None else 9999,
        ),
    )
    limited = [row["model_id"] for row in summary.get("models", []) if row["rate_limited"] > 0 and row["successes"] == 0]
    if not best:
        lines = [
            "Aucune recommandation qualité fiable : il faut lancer la phase quality sur les modèles disponibles."
        ]
        if exploitable:
            lines.append(
                "- Meilleur modèle gratuit réellement exploitable pour l'instant : "
                f"`{exploitable[0]['model_id']}` "
                f"({exploitable[0]['successes']} réponse(s) 200, "
                f"{exploitable[0]['rate_limited']} réponse(s) 429)."
            )
        if limited:
            lines.append(
                "- Modèles trop limités à éviter temporairement : "
                + ", ".join(f"`{model}`" for model in limited)
                + "."
            )
        if exploitable:
            lines.append(
                "- Modèle à tester ensuite localement avec Ollama : "
                f"`{exploitable[0].get('local_equivalent_ollama', '')}`."
            )
        return "\n".join(lines)
    qualifier = "meilleur candidat provisoire"
    if best["model_id"] == "deepseek/deepseek-v4-flash:free":
        qualifier = "meilleur candidat provisoire, pas une conclusion définitive"
    lines = [
        f"- Meilleur modèle cloud gratuit pour nos tests : `{best['model_id']}` est le {qualifier}, "
        f"avec {best['successes']} réponses HTTP 200."
    ]
    if local:
        lines.append(
            "- Meilleur modèle à reproduire localement avec Ollama : "
            f"`{local.get('local_equivalent_ollama', '')}`."
        )
    optional_models = [
        row["model_id"]
        for row in summary.get("models", [])
        if row["successes"] > 0 and row["successes"] < 3 or row["rate_limited"] > row["successes"]
    ]
    avoided_models = [
        row["model_id"]
        for row in summary.get("models", [])
        if row["model_not_found"] > 0 or (row["successes"] == 0 and row["api_errors"] + row["timeouts"] > 0)
    ]
    if optional_models:
        lines.append("- À garder seulement en option : " + ", ".join(f"`{model}`" for model in optional_models) + ".")
    if avoided_models:
        lines.append("- À éviter pour le prochain run safe : " + ", ".join(f"`{model}`" for model in avoided_models) + ".")
    return "\n".join(lines)


def _detailed_results_table(results: list[dict[str, Any]]) -> str:
    lines = [
        "| Modèle | Question | Statut | HTTP | Temps | Sources | Refus absent OK | Score RAG | Extrait | Erreur |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in results:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["model_id"]),
                    str(row["question_id"]),
                    str(row["status"]),
                    _value(row["http_status_code"]),
                    _seconds(row["response_time_seconds"]),
                    "oui" if row["contains_sources"] else "non",
                    "oui" if row["refused_when_absent"] else "non",
                    _value(row["auto_rag_quality_score"]),
                    _clean_markdown_cell(row.get("answer_excerpt") or ""),
                    _clean_markdown_cell(row.get("error_message") or ""),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _answer_excerpts_table(results: list[dict[str, Any]]) -> str:
    rows = [row for row in results if row.get("answer_excerpt")]
    if not rows:
        return "Aucune réponse textuelle disponible dans ce rapport."
    lines = [
        "| Modèle | Question | Extrait de réponse |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['model_id']} | {row['question_id']} | {_clean_markdown_cell(row.get('answer_excerpt') or '')} |"
        )
    return "\n".join(lines)


def _value(value: Any) -> str:
    return "n/a" if value is None else str(value)


def _answer_excerpt(answer: str, max_length: int = 500) -> str:
    cleaned = " ".join(answer.split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 3].rstrip() + "..."


def _rate(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.0f}%"


def _seconds(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.3f}s"


def _model_status_label(row: dict[str, Any]) -> str:
    if row["successes"] >= 3 and row["rate_limited"] == 0 and row["model_not_found"] == 0:
        return "stable provisoire"
    if row["successes"] >= 3:
        return "exploitable avec réserves"
    if row["model_not_found"] > 0:
        return "introuvable"
    if row["rate_limited"] > 0:
        return "limité par quota"
    if row["successes"] > 0:
        return "données insuffisantes"
    return "échec"


def _clean_markdown_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")[:180]


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark RAG OpenRouter avec contextes fictifs.")
    parser.add_argument("--include-disabled", action="store_true", help="Inclure les modèles désactivés dans la config.")
    parser.add_argument("--max-requests", type=int, default=None, help="Limiter explicitement le nombre de requêtes chat.")
    parser.add_argument("--max-models", type=int, default=None, help="Nombre maximal de modèles à tester.")
    parser.add_argument("--max-questions", type=int, default=None, help="Nombre maximal de questions à tester.")
    parser.add_argument("--models", nargs="+", default=None, help="Liste explicite de model_id OpenRouter à tester.")
    parser.add_argument("--request-delay-seconds", type=float, default=None, help="Délai entre deux appels chat.")
    parser.add_argument("--smoke-test", action="store_true", help="Tester 1 à 2 modèles valides sur 1 question.")
    parser.add_argument("--safe", action="store_true", help="Limiter à 3 modèles, 3 questions et au moins 35s entre appels.")
    parser.add_argument("--availability", action="store_true", help="Phase 1: tester la disponibilité de plusieurs modèles sur 1 question.")
    parser.add_argument(
        "--quality-from-last-availability",
        action="store_true",
        help="Phase 2: tester la qualité des modèles ayant réussi le dernier availability benchmark.",
    )
    parser.add_argument(
        "--hallucination-check",
        action="store_true",
        help="Mini-test final anti-hallucination sur les trois modèles exploitables.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    try:
        output = run_benchmark(
            settings,
            include_disabled=args.include_disabled,
            max_requests=args.max_requests,
            max_models=args.max_models,
            max_questions=args.max_questions,
            model_ids=args.models,
            request_delay_seconds=args.request_delay_seconds,
            smoke_test=args.smoke_test,
            safe=args.safe,
            availability=args.availability,
            quality_from_last_availability=args.quality_from_last_availability,
            hallucination_check=args.hallucination_check,
        )
    except Exception as exc:
        logger.error("%s", exc)
        return 1

    print("Benchmark OpenRouter terminé.")
    print(f"Mode: {output['run']['mode']}")
    print(f"JSON: {output['output_paths']['json']}")
    print(f"CSV: {output['output_paths']['csv']}")
    print(f"Markdown: {output['output_paths']['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
