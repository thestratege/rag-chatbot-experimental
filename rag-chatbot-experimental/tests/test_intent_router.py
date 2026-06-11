from app.intent_router import IntentRouter


def test_detects_greeting_without_rag() -> None:
    result = IntentRouter().classify("Bonjour")

    assert result.intent == "greeting"


def test_detects_documentary_question() -> None:
    result = IntentRouter().classify("Quelle est la procédure de demande d'accès ?")

    assert result.intent == "rag_question"
    assert result.profile == "access_request"


def test_detects_documentary_summary_question() -> None:
    result = IntentRouter().classify("Résume les principales procédures disponibles dans les documents.")

    assert result.intent == "rag_question"
    assert result.profile == "global_summary"


def test_detects_usage_policy_question() -> None:
    result = IntentRouter().classify("Quelles sont les bonnes pratiques d’utilisation ?")

    assert result.intent == "rag_question"
    assert result.profile == "usage_policy"


def test_detects_capability_question_with_typographic_apostrophe() -> None:
    result = IntentRouter().classify("Je veux comprendre comment tu peux m’aider.")

    assert result.intent == "capability_question"
    assert result.profile == "capability_question"


def test_detects_capability_question_with_simple_apostrophe() -> None:
    result = IntentRouter().classify("Je veux comprendre comment tu peux m'aider.")

    assert result.intent == "capability_question"
    assert result.profile == "capability_question"


def test_detects_capability_question_with_missing_apostrophe() -> None:
    result = IntentRouter().classify("comment tu peux maider")

    assert result.intent == "capability_question"
    assert result.profile == "capability_question"


def test_detects_access_request_with_normalized_spelling() -> None:
    result = IntentRouter().classify("comment demander un acces")

    assert result.intent == "rag_question"
    assert result.profile == "access_request"


def test_detects_access_request_with_typo() -> None:
    result = IntentRouter().classify("comment demender un acces")

    assert result.intent == "rag_question"
    assert result.profile == "access_request"


def test_detects_password_reset_variants() -> None:
    router = IntentRouter()

    first = router.classify("mot de passe oublie")
    second = router.classify("reinitialiser mot passe")

    assert first.intent == "rag_question"
    assert first.profile == "password_reset"
    assert second.intent == "rag_question"
    assert second.profile == "password_reset"


def test_detects_usage_policy_without_full_sentence() -> None:
    result = IntentRouter().classify("bonnes pratiques utilisation")

    assert result.intent == "rag_question"
    assert result.profile == "usage_policy"


def test_detects_global_summary_with_typo() -> None:
    result = IntentRouter().classify("resumer les procedures")

    assert result.intent == "rag_question"
    assert result.profile == "global_summary"


def test_detects_clarification_needed() -> None:
    result = IntentRouter().classify("Aide")

    assert result.intent == "clarification_needed"


def test_detects_out_of_scope() -> None:
    result = IntentRouter().classify("Quelle est la météo aujourd'hui ?")

    assert result.intent == "out_of_scope"
