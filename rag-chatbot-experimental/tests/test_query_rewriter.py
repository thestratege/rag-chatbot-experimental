from app.config import Settings
from app.query_rewriter import QueryRewriter


class FakeRewriteClient:
    def __init__(self, answer: str = "", error: Exception | None = None) -> None:
        self.answer = answer
        self.error = error
        self.calls: list[tuple[str, list[str]]] = []

    def rewrite(self, question: str, history: list[str]) -> str:
        self.calls.append((question, history))
        if self.error:
            raise self.error
        return self.answer


def test_query_rewriter_makes_contextual_question_autonomous() -> None:
    client = FakeRewriteClient("Quelle est la procédure interne pour demander un accès SharePoint ?")
    rewriter = QueryRewriter(Settings(rag_query_rewrite_enabled=True), client=client)

    result = rewriter.rewrite("Et pour les accès ?", ["Comment utiliser SharePoint ?"])

    assert result.used is True
    assert result.rewritten_question.startswith("Quelle est la procédure")
    assert client.calls


def test_query_rewriter_falls_back_to_original_on_error() -> None:
    rewriter = QueryRewriter(
        Settings(rag_query_rewrite_enabled=True),
        client=FakeRewriteClient(error=RuntimeError("Ollama indisponible")),
    )

    result = rewriter.rewrite("Et si je suis gestionnaire ?", ["Nous parlons des demandes d'accès."])

    assert result.used is False
    assert result.rewritten_question == "Et si je suis gestionnaire ?"


def test_query_rewriter_skips_llm_when_disabled() -> None:
    client = FakeRewriteClient("Ne doit pas être utilisé")
    result = QueryRewriter(Settings(rag_query_rewrite_enabled=False), client=client).rewrite(
        "Et pour les accès ?",
        ["Contexte"],
    )

    assert result.used is False
    assert client.calls == []


def test_query_rewriter_skips_clear_autonomous_question() -> None:
    client = FakeRewriteClient("Ne doit pas être utilisé")
    result = QueryRewriter(Settings(rag_query_rewrite_enabled=True), client=client).rewrite(
        "Comment demander un accès ?",
        ["Contexte antérieur sans rapport."],
    )

    assert result.used is False
    assert client.calls == []
