from __future__ import annotations

from dataclasses import dataclass, field

from app.config import Settings, settings
from app.intent_router import IntentRouter
from app.openrouter_client import OpenRouterClient
from app.rag_pipeline import NOT_FOUND_ANSWER
from app.schemas import ChatResponse, IntentName, ProviderName, Source


ABSENT_WITH_SOURCES = (
    "Je ne trouve pas cette information dans les documents fournis.\n\n"
    "Sources :\n"
    "- Aucune source pertinente trouvée."
)
CAPABILITY_ANSWER = (
    "Je peux vous aider à retrouver des informations dans les documents internes. "
    "Vous pouvez me poser une question sur une procédure, un accès, un rapport, "
    "une politique ou une information contenue dans les documents disponibles. "
    "Lorsque je trouve une réponse, je fournis aussi les sources utilisées."
)


@dataclass(frozen=True)
class ProviderAnswer:
    answer: str
    sources: list[Source]
    provider: ProviderName
    diagnostics: dict[str, object] = field(default_factory=dict)


class OpenRouterRAGLLMClient:
    """LLM adapter for RAG generation through OpenRouter when explicitly allowed."""

    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self.client = OpenRouterClient(config)

    def generate_answer(self, question: str, context: str) -> str:
        response = self.client.chat_completion(
            self.config.openrouter_model,
            [
                {
                    "role": "system",
                    "content": (
                        "Tu es un assistant documentaire interne. Tu dois répondre uniquement à partir "
                        "du contexte fourni. Si l'information n'est pas présente, réponds exactement : "
                        "'Je ne trouve pas cette information dans les documents fournis.' Réponds en "
                        "français et cite les sources utilisées."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"CONTEXTE:\n{context}\n\nQUESTION:\n{question}\n\n"
                        "Réponds uniquement avec les informations du CONTEXTE."
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=700,
        )
        return response.content

    def is_available(self) -> bool:
        return bool(self.config.openrouter_api_key and self.config.openrouter_enabled)


class ProviderRouter:
    """Chooses the LLM provider used by the conversational endpoint."""

    def __init__(self, config: Settings = settings) -> None:
        self.config = config

    @property
    def provider(self) -> ProviderName:
        provider = self.config.llm_provider.lower()
        if provider in {"mock", "retrieval_only", "openrouter", "ollama"}:
            return provider  # type: ignore[return-value]
        return "mock"

    def answer_without_rag(self, message: str, intent: IntentName) -> ProviderAnswer:
        answer = _non_rag_answer(message, intent)
        return ProviderAnswer(answer=answer, sources=[], provider=self.provider)

    def answer_with_mock_rag(self, message: str, routing_profile: str | None = None) -> ProviderAnswer:
        profile = routing_profile or IntentRouter().classify(message).profile
        if profile == "global_summary":
            return _mock_global_summary()
        if profile == "access_request":
            return _mock_access_answer()
        if profile == "password_reset":
            return _mock_password_answer()
        if profile == "report_creation":
            return _mock_report_answer()
        if profile == "support_help":
            return _mock_support_answer()
        if profile == "usage_policy":
            return _mock_usage_policy_answer()
        return ProviderAnswer(answer=ABSENT_WITH_SOURCES, sources=[], provider="mock")

    def openrouter_document_context_allowed(self) -> bool:
        return self.config.openrouter_allow_document_context


def normalize_absent_answer(response: ChatResponse) -> ChatResponse:
    if NOT_FOUND_ANSWER.lower() in response.answer.lower() and not response.sources:
        return ChatResponse(answer=ABSENT_WITH_SOURCES, sources=[])
    return response


def _non_rag_answer(message: str, intent: IntentName) -> str:
    if intent == "greeting":
        return (
            "Bonjour. Je peux vous aider à retrouver une information dans les documents internes. "
            "Posez-moi une question documentaire quand vous êtes prêt."
        )
    if intent == "small_talk":
        return (
            "Je vais bien, merci. Mon rôle est surtout de vous aider à retrouver rapidement "
            "des informations sourcées dans les documents disponibles."
        )
    if intent == "capability_question":
        return CAPABILITY_ANSWER
    if intent == "clarification_needed":
        return (
            "Pouvez-vous préciser votre demande ? Par exemple, indiquez la procédure, le document "
            "ou le sujet que vous souhaitez vérifier."
        )
    if intent == "out_of_scope":
        return (
            "Je suis conçu pour répondre aux questions liées aux documents internes. "
            "Reformulez votre demande avec un sujet documentaire si vous voulez que je recherche une source."
        )
    return (
        "Je n'ai pas assez d'éléments pour répondre correctement. Pouvez-vous reformuler votre question "
        "en précisant le document ou l'information recherchée ?"
    )


def _mock_source(file_name: str, chunk_id: str, excerpt: str, score: float = 0.95) -> Source:
    return Source(
        file_name=file_name,
        page=None,
        chunk_id=chunk_id,
        excerpt=excerpt,
        score=score,
    )


def _mock_global_summary() -> ProviderAnswer:
    return ProviderAnswer(
        answer=(
            "Les documents disponibles couvrent principalement la demande d'accès, "
            "la réinitialisation du mot de passe, la création de rapport, le support utilisateur "
            "et la politique d'utilisation des outils internes.\n\n"
            "Sources :\n"
            "- procedure_acces.txt, chunk sample-acces-1\n"
            "- procedure_mot_de_passe.txt, chunk sample-password-1\n"
            "- procedure_creation_rapport.txt, chunk sample-report-1\n"
            "- faq_support.txt, chunk sample-support-1\n"
            "- politique_utilisation.txt, chunk sample-policy-1"
        ),
        sources=[
            _mock_source(
                "procedure_acces.txt",
                "sample-acces-1",
                "Demande d'accès avec nom, service, rôle demandé et justification opérationnelle.",
            ),
            _mock_source(
                "procedure_mot_de_passe.txt",
                "sample-password-1",
                "Réinitialisation de mot de passe via le support ou la procédure interne.",
            ),
            _mock_source(
                "procedure_creation_rapport.txt",
                "sample-report-1",
                "Création de rapport avec informations nécessaires et validation.",
            ),
            _mock_source(
                "faq_support.txt",
                "sample-support-1",
                "Support utilisateur pour incidents, assistance et demandes techniques.",
            ),
            _mock_source(
                "politique_utilisation.txt",
                "sample-policy-1",
                "Politique d'utilisation responsable des outils internes.",
            ),
        ],
        provider="mock",
    )


def _mock_access_answer() -> ProviderAnswer:
    return ProviderAnswer(
        answer=(
            "Pour demander un accès, l'utilisateur doit transmettre une demande au support "
            "avec son nom, son service, le rôle demandé et une justification opérationnelle.\n\n"
            "Sources :\n"
            "- procedure_acces.txt, chunk sample-acces-1"
        ),
        sources=[
            _mock_source(
                "procedure_acces.txt",
                "sample-acces-1",
                "Toute demande d'accès doit préciser le nom du demandeur, le service, "
                "le rôle attendu et la justification opérationnelle.",
                score=0.98,
            )
        ],
        provider="mock",
    )


def _mock_password_answer() -> ProviderAnswer:
    return ProviderAnswer(
        answer=(
            "Pour réinitialiser un mot de passe, l'utilisateur doit contacter le support ou "
            "suivre la procédure interne de réinitialisation prévue.\n\n"
            "Sources :\n"
            "- procedure_mot_de_passe.txt, chunk sample-password-1"
        ),
        sources=[
            _mock_source(
                "procedure_mot_de_passe.txt",
                "sample-password-1",
                "Le support vérifie l'identité de l'utilisateur avant d'envoyer un lien temporaire "
                "de réinitialisation.",
                score=0.96,
            )
        ],
        provider="mock",
    )


def _mock_report_answer() -> ProviderAnswer:
    return ProviderAnswer(
        answer=(
            "Pour créer un rapport, l'utilisateur doit suivre les étapes prévues, renseigner "
            "les informations nécessaires et soumettre le rapport selon la procédure interne.\n\n"
            "Sources :\n"
            "- procedure_creation_rapport.txt, chunk sample-report-1"
        ),
        sources=[
            _mock_source(
                "procedure_creation_rapport.txt",
                "sample-report-1",
                "Le rapport mensuel inclut le périmètre, la période, les indicateurs, les écarts "
                "et les actions proposées.",
            )
        ],
        provider="mock",
    )


def _mock_support_answer() -> ProviderAnswer:
    return ProviderAnswer(
        answer=(
            "En cas de problème technique, l'utilisateur doit contacter le support en décrivant "
            "le problème, le contexte et l'urgence de la demande.\n\n"
            "Sources :\n"
            "- faq_support.txt, chunk sample-support-1"
        ),
        sources=[
            _mock_source(
                "faq_support.txt",
                "sample-support-1",
                "Une demande doit contenir une description claire, l'impact observé, "
                "le service concerné et, si possible, une capture d'écran.",
                score=0.94,
            )
        ],
        provider="mock",
    )


def _mock_usage_policy_answer() -> ProviderAnswer:
    return ProviderAnswer(
        answer=(
            "Les bonnes pratiques d'utilisation consistent à utiliser les outils internes de "
            "manière responsable, à respecter les règles de sécurité, à ne pas partager ses "
            "accès et à signaler tout problème au support.\n\n"
            "Sources :\n"
            "- politique_utilisation.txt, chunk sample-policy-1"
        ),
        sources=[
            _mock_source(
                "politique_utilisation.txt",
                "sample-policy-1",
                "Les outils internes doivent être utilisés uniquement dans un cadre professionnel. "
                "Le partage d'identifiants est interdit.",
                score=0.97,
            )
        ],
        provider="mock",
    )
