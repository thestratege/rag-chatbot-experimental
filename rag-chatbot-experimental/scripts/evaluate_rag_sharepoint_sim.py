from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUESTIONS = ROOT / "tests" / "evaluation_questions_sharepoint_sim.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Évaluation locale du RAG SharePoint simulé.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8013")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--token", default="")
    parser.add_argument("--profile", default="demo-user")
    parser.add_argument(
        "--permission-mode",
        choices=("open", "filtered"),
        default="open",
        help="Sélectionne les cas compatibles avec le mode de permissions actif.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    questions = [
        case
        for case in json.loads(args.questions.read_text(encoding="utf-8"))
        if case.get("enabled", True) and args.permission_mode in case.get("permission_modes", ["open", "filtered"])
    ]
    results = [_evaluate(args, case) for case in questions]
    successes = sum(bool(result["success"]) for result in results)
    average = sum(float(result["response_time_seconds"]) for result in results) / len(results) if results else 0
    refusals = sum(bool(result["refusal_correct"]) for result in results)
    sources = sum(bool(result["sources_correct"]) for result in results)
    print(f"Questions testées : {len(results)}")
    print(f"Mode permissions attendu : {args.permission_mode}")
    print(f"Réussies : {successes}")
    print(f"Échecs : {len(results) - successes}")
    print(f"Temps moyen : {average:.2f} s")
    print(f"Refus corrects : {refusals}")
    print(f"Sources correctes : {sources}")
    for result in results:
        print(f"- {result['id']}: {'OK' if result['success'] else 'ÉCHEC'} ({result['detail']})")
    return 0 if successes == len(results) else 1


def _evaluate(args: argparse.Namespace, case: dict[str, object]) -> dict[str, object]:
    payload = json.dumps(
        {"conversation_id": None, "message": case["question"], "mode": "auto"}
    ).encode("utf-8")
    profile = str(case.get("profile", args.profile))
    headers = {"Content-Type": "application/json", "X-Demo-Profile": profile}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    request = urllib.request.Request(f"{args.base_url.rstrip('/')}/api/chat", data=payload, headers=headers)
    started_at = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as exc:
        return _result(case, time.perf_counter() - started_at, False, False, False, str(exc))

    answer = str(data.get("answer", ""))
    source_names = {str(source.get("file_name")) for source in data.get("sources", [])}
    expected_sources = set(case.get("expected_sources_any", []))
    forbidden_sources = set(case.get("forbidden_sources", []))
    must_contain = [str(value) for value in case.get("must_contain_any", [])]
    refusal_expected = case.get("expected_behavior") == "refusal"
    refusal_correct = ("Je ne trouve pas" in answer) == refusal_expected
    sources_correct = (
        not expected_sources or bool(source_names.intersection(expected_sources))
    ) and not source_names.intersection(forbidden_sources)
    content_correct = not must_contain or any(value.lower() in answer.lower() for value in must_contain)
    provider_correct = data.get("provider") == "ollama"
    success = refusal_correct and sources_correct and content_correct and provider_correct
    confidence = data.get("rag_confidence")
    detail = f"provider={data.get('provider')}, profile={profile}, sources={sorted(source_names)}, confidence={confidence}"
    result = _result(case, time.perf_counter() - started_at, success, refusal_correct, sources_correct, detail)
    result["confidence"] = confidence
    return result


def _result(
    case: dict[str, object],
    elapsed: float,
    success: bool,
    refusal_correct: bool,
    sources_correct: bool,
    detail: str,
) -> dict[str, object]:
    return {
        "id": case["id"],
        "success": success,
        "response_time_seconds": elapsed,
        "refusal_correct": refusal_correct,
        "sources_correct": sources_correct,
        "detail": detail,
    }


if __name__ == "__main__":
    raise SystemExit(main())
