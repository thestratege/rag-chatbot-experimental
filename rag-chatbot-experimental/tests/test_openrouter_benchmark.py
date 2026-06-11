from scripts import benchmark_openrouter_models as benchmark


def test_benchmark_contexts_do_not_reference_real_documents_folder() -> None:
    contexts = benchmark._load_contexts()
    formatted_context = benchmark._format_context(contexts)

    assert "data/documents" not in formatted_context
    assert "procedure_demande_acces.pdf" in formatted_context


def test_source_detection_accepts_file_and_chunk_aliases() -> None:
    contexts = [
        {
            "source_id": "SRC-TEST-001",
            "file_name": "procedure_test.pdf",
            "page": 1,
            "chunk_id": "test-c1",
            "text": "Contenu fictif.",
        }
    ]
    aliases = benchmark._expected_source_aliases(["SRC-TEST-001"], benchmark._source_aliases(contexts))

    answer = "Réponse courte.\n\nSources : procedure_test.pdf, chunk test-c1"

    assert benchmark._contains_sources(answer, aliases, benchmark._source_markers(contexts))
    assert benchmark._expected_source_hits(answer, aliases) == 1


def test_source_detection_accepts_required_source_format_markers() -> None:
    contexts = benchmark._load_contexts()
    markers = benchmark._source_markers(contexts)
    aliases = benchmark._expected_source_aliases(["SRC-ACCES-001"], benchmark._source_aliases(contexts))

    assert benchmark._contains_sources("Réponse.\n\nSources :\n- [procedure_demande_acces.pdf, page 2, acces-p2-c1]", aliases, markers)
    assert benchmark._contains_sources("Réponse.\n\nSource : procedure_demande_acces.pdf", [], markers)
    assert benchmark._contains_sources("Réponse avec chunk acces-p2-c1.", [], markers)
    assert benchmark._contains_sources("Réponse avec page 2.", [], markers)


def test_refusal_detection_for_absent_information() -> None:
    assert benchmark._refused_when_absent(benchmark.REFUSAL_ANSWER, should_refuse_if_absent=True)


def test_exact_absent_refusal_accepts_spacing_variants() -> None:
    variants = [
        benchmark.EXPECTED_ABSENT_ANSWER,
        "Je ne trouve pas cette information dans les documents fournis.\nSources :\n- Aucune source pertinente trouvée.",
        "Je ne trouve pas cette information dans les documents fournis. Sources : - Aucune source pertinente trouvée.",
        "Je ne trouve pas cette information dans les documents fournis.   Sources:   -   Aucune source pertinente trouvée.",
        "  Je ne trouve pas cette information dans les documents fournis\n\nSources :\n - Aucune source pertinente trouvée.  ",
    ]

    assert all(benchmark._exact_absent_refusal(answer) for answer in variants)


def test_hallucination_check_classification() -> None:
    markers = benchmark._source_markers(benchmark._load_contexts())

    assert (
        benchmark._hallucination_check_result(
            answer="Je ne trouve pas cette information dans les documents fournis. Sources : - Aucune source pertinente trouvée.",
            status=benchmark.STATUS_SUCCESS,
            question_id="HALLUCINATION_FINAL_ABSENT",
            all_source_markers=markers,
        )
        == benchmark.HALLUCINATION_RESULT_CORRECT_REFUSAL
    )
    assert (
        benchmark._hallucination_check_result(
            answer="La politique prévoit un remboursement sous 30 jours.",
            status=benchmark.STATUS_SUCCESS,
            question_id="HALLUCINATION_FINAL_ABSENT",
            all_source_markers=markers,
        )
        == benchmark.HALLUCINATION_RESULT_INVENTED_ANSWER
    )
    assert (
        benchmark._hallucination_check_result(
            answer="Je ne trouve pas cette information.\n\nSources :\n- [procedure_demande_acces.pdf, page 2, acces-p2-c1]",
            status=benchmark.STATUS_SUCCESS,
            question_id="HALLUCINATION_FINAL_ABSENT",
            all_source_markers=markers,
        )
        == benchmark.HALLUCINATION_RESULT_NON_RELEVANT_SOURCE
    )


def test_system_prompt_requires_exact_source_format() -> None:
    assert "Sources :" in benchmark.SYSTEM_PROMPT
    assert "- [file_name, page X, chunk_id]" in benchmark.SYSTEM_PROMPT
    assert "Aucune source pertinente trouvée" in benchmark.SYSTEM_PROMPT


def test_markdown_report_contains_rankings_and_recommendations() -> None:
    models = [
        {
            "model_id": "qwen/qwen3-next-80b-a3b-instruct:free",
            "provider_family": "Qwen",
            "local_equivalent_ollama": "qwen3:8b ou qwen3:14b",
        }
    ]
    results = [
        {
            "run_id": "TEST",
            "timestamp": "2026-05-19T00:00:00",
            "model_id": "qwen/qwen3-next-80b-a3b-instruct:free",
            "provider_family": "Qwen",
            "local_equivalent_ollama": "qwen3:8b ou qwen3:14b",
            "question_id": "Q1",
            "question": "Question fictive ?",
            "status": benchmark.STATUS_SUCCESS,
            "http_status_code": 200,
            "response_time_seconds": 1.2,
            "answer": "Réponse avec source procedure_test.pdf.",
            "error_message": None,
            "expected_answer_hint": "",
            "expected_sources": ["SRC-TEST-001"],
            "answer_length_chars": 36,
            "auto_quality_score": 8.5,
            "auto_rag_quality_score": 4.5,
            "contains_sources": True,
            "expected_source_hits": 1,
            "refused_when_absent": False,
            "should_refuse_if_absent": False,
            "error": None,
        }
    ]
    summary = benchmark._summarize_results(
        configured_models=models,
        discovered_models=[{"id": "qwen/qwen3-next-80b-a3b-instruct:free"}],
        selected_models=models,
        skipped_models=[],
        results=results,
    )
    report = benchmark._markdown_report(
        {
            "run": {
                "run_id": "TEST",
                "mode": "safe",
                "models_tested": 1,
                "questions_tested": 1,
                "request_delay_seconds": 8,
            },
            "summary": summary,
            "results": results,
        }
    )

    assert "Résumé exécutif" in report
    assert "qwen/qwen3-next-80b-a3b-instruct:free" in report
    assert "Recommandation provisoire" in report


def test_skipped_models_are_detected_before_chat_requests() -> None:
    models = [
        {"model_id": "missing/model:free", "enabled": True},
        {"model_id": "valid/model:free", "enabled": True},
    ]

    skipped = benchmark._skipped_models(models, {"valid/model:free"})

    assert len(skipped) == 1
    assert skipped[0]["model_id"] == "missing/model:free"
    assert skipped[0]["status"] == benchmark.SKIPPED_MODEL_STATUS


def test_models_from_cli_preserve_order_and_reject_auto_router() -> None:
    selected = benchmark._models_from_ids(
        ["qwen/qwen3-next-80b-a3b-instruct:free", "openai/gpt-oss-20b:free"],
        [{"model_id": "openai/gpt-oss-20b:free", "provider_family": "OpenAI OSS"}],
    )

    assert [model["model_id"] for model in selected] == [
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "openai/gpt-oss-20b:free",
    ]
    assert selected[1]["provider_family"] == "OpenAI OSS"

    try:
        benchmark._models_from_ids(["openrouter/free"], [])
    except ValueError as exc:
        assert "openrouter/free" in str(exc)
    else:
        raise AssertionError("openrouter/free must be rejected")


def test_safe_defaults_are_conservative() -> None:
    from app.config import Settings

    config = Settings(openrouter_request_delay_seconds=8, openrouter_max_questions_per_run=5)

    assert benchmark._effective_max_models(
        config,
        max_models=None,
        smoke_test=False,
        safe=True,
        availability=False,
        quality_from_last_availability=False,
        hallucination_check=False,
        candidate_count=3,
    ) == 3
    assert benchmark._effective_max_questions(
        config,
        max_questions=None,
        smoke_test=False,
        safe=True,
        availability=False,
        quality_from_last_availability=False,
        hallucination_check=False,
    ) == 3
    assert benchmark._effective_delay(config, request_delay_seconds=None, safe=True) == 35.0


def test_availability_and_quality_mode_defaults() -> None:
    from app.config import Settings

    config = Settings()

    assert benchmark._effective_max_questions(
        config,
        max_questions=None,
        smoke_test=False,
        safe=False,
        availability=True,
        quality_from_last_availability=False,
        hallucination_check=False,
    ) == 1
    assert benchmark._effective_max_questions(
        config,
        max_questions=4,
        smoke_test=False,
        safe=False,
        availability=False,
        quality_from_last_availability=True,
        hallucination_check=False,
    ) == 4
    assert benchmark._effective_max_models(
        config,
        max_models=None,
        smoke_test=False,
        safe=False,
        availability=True,
        quality_from_last_availability=False,
        hallucination_check=False,
        candidate_count=9,
    ) == 9

    assert benchmark._effective_max_questions(
        config,
        max_questions=None,
        smoke_test=False,
        safe=False,
        availability=False,
        quality_from_last_availability=False,
        hallucination_check=True,
    ) == 1


def test_mode_flags_are_mutually_exclusive() -> None:
    try:
        benchmark._validate_mode_flags(
            smoke_test=False,
            safe=True,
            availability=True,
            quality_from_last_availability=False,
            hallucination_check=False,
        )
    except ValueError as exc:
        assert "--availability" in str(exc)
    else:
        raise AssertionError("exclusive modes should raise")
