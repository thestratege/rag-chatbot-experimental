from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from app.schemas import IntentName


ACCEPT_THRESHOLD = 0.65
CLARIFICATION_THRESHOLD = 0.40

INTENT_PROFILES: dict[str, dict[str, Any]] = {
    "capability_question": {
        "description": "question sur ce que le chatbot peut faire et comment il peut aider",
        "keywords": ["aider", "faire", "sert", "fonctionne", "capacite", "comprendre", "peux"],
    },
    "access_request": {
        "description": "demande d'accès, permission, rôle demandé, justification opérationnelle",
        "keywords": ["acces", "demande", "permission", "autorisation", "role", "justification"],
    },
    "password_reset": {
        "description": "mot de passe oublié, réinitialisation, problème de connexion",
        "keywords": ["mot", "passe", "mdp", "password", "reinitialiser", "connexion", "oublie"],
    },
    "report_creation": {
        "description": "création, production ou soumission de rapport",
        "keywords": ["rapport", "creation", "creer", "produire", "soumettre"],
    },
    "support_help": {
        "description": "support, assistance, aide, incident ou problème technique",
        "keywords": ["support", "assistance", "aide", "probleme", "incident", "technique"],
    },
    "usage_policy": {
        "description": "politique d'utilisation, bonnes pratiques, règles, outils internes",
        "keywords": ["politique", "utilisation", "bonnes", "pratiques", "regles", "outils", "interne"],
    },
    "global_summary": {
        "description": "résumé global des documents et des principales procédures disponibles",
        "keywords": ["resume", "synthese", "documents", "procedures", "principales", "disponibles"],
    },
}

PROFILE_TO_INTENT: dict[str, IntentName] = {
    "capability_question": "capability_question",
    "access_request": "rag_question",
    "password_reset": "rag_question",
    "report_creation": "rag_question",
    "support_help": "rag_question",
    "usage_policy": "rag_question",
    "global_summary": "rag_question",
}

GREETING_TERMS = {"bonjour", "salut", "hello", "coucou", "bonsoir", "bon matin", "hi"}
SMALL_TALK_TERMS = {"merci", "comment ca va", "ca va", "qui es tu"}
AMBIGUOUS_MESSAGES = {"aide", "help", "explique", "plus", "details", "peux tu m aider", "je ne comprends pas"}
OUT_OF_SCOPE_TERMS = {
    "meteo",
    "blague",
    "recette",
    "film",
    "musique",
    "sport",
    "bourse",
    "bitcoin",
    "capitale de",
}
ABSENT_DOCUMENTARY_TERMS = {
    "remboursement",
    "billet avion",
    "billets avion",
    "frais de deplacement",
    "salaire",
    "hotel",
    "telephone personnel",
    "informations personnelles",
    "information personnelle",
    "teletravail complet",
}


@dataclass(frozen=True)
class IntentResult:
    intent: IntentName
    confidence: float
    reason: str
    profile: str | None = None
    normalized_text: str = ""


@dataclass(frozen=True)
class ProfileMatch:
    profile: str
    score: float


class IntentRouter:
    """Profile-based intent router with lightweight fuzzy matching."""

    def classify(self, message: str) -> IntentResult:
        normalized = normalize_text(message)
        has_question_mark = "?" in message
        if not normalized:
            return IntentResult("clarification_needed", 1.0, "Message vide.", normalized_text=normalized)

        if _is_greeting(normalized):
            return IntentResult("greeting", 0.95, "Salutation détectée.", normalized_text=normalized)

        if normalized in AMBIGUOUS_MESSAGES:
            return IntentResult(
                "clarification_needed",
                0.75,
                "Message trop court ou ambigu.",
                normalized_text=normalized,
            )

        if _contains_any_term(normalized, ABSENT_DOCUMENTARY_TERMS):
            return IntentResult(
                "rag_question",
                0.90,
                "Sujet documentaire non couvert par le jeu de démonstration.",
                profile="unknown_documentary",
                normalized_text=normalized,
            )

        if _contains_any_term(normalized, SMALL_TALK_TERMS):
            return IntentResult("small_talk", 0.85, "Petite conversation détectée.", normalized_text=normalized)

        if _contains_any_term(normalized, OUT_OF_SCOPE_TERMS):
            return IntentResult(
                "out_of_scope",
                0.80,
                "Sujet hors périmètre documentaire.",
                normalized_text=normalized,
            )

        best_match = _best_profile_match(normalized)
        if best_match and best_match.score >= ACCEPT_THRESHOLD:
            return IntentResult(
                PROFILE_TO_INTENT[best_match.profile],
                best_match.score,
                f"Profil d'intention détecté: {best_match.profile}.",
                profile=best_match.profile,
                normalized_text=normalized,
            )

        if best_match and best_match.score >= CLARIFICATION_THRESHOLD:
            return IntentResult(
                "clarification_needed",
                best_match.score,
                f"Profil possible mais incertain: {best_match.profile}.",
                profile=best_match.profile,
                normalized_text=normalized,
            )

        if has_question_mark:
            return IntentResult("unknown", 0.35, "Question détectée, périmètre incertain.", normalized_text=normalized)

        return IntentResult("unknown", 0.25, "Intention non reconnue.", normalized_text=normalized)


def normalize_text(message: str) -> str:
    lowered = message.strip().lower().replace("’", "'").replace("`", "'")
    apostrophes_as_spaces = lowered.replace("'", " ")
    without_accents = "".join(
        character
        for character in unicodedata.normalize("NFKD", apostrophes_as_spaces)
        if not unicodedata.combining(character)
    )
    without_punctuation = re.sub(r"[^a-z0-9\s]", " ", without_accents)
    return " ".join(without_punctuation.split())


def _is_greeting(text: str) -> bool:
    return text in GREETING_TERMS


def _contains_any_term(text: str, terms: set[str]) -> bool:
    return any(normalize_text(term) in text for term in terms)


def _best_profile_match(text: str) -> ProfileMatch | None:
    matches = [_score_profile(text, profile, data) for profile, data in INTENT_PROFILES.items()]
    return max(matches, key=lambda match: match.score) if matches else None


def _score_profile(text: str, profile: str, data: dict[str, Any]) -> ProfileMatch:
    description = normalize_text(str(data["description"]))
    keywords = [normalize_text(keyword) for keyword in data["keywords"]]
    keyword_score = _keyword_score(text, keywords)
    description_score = SequenceMatcher(None, text, description).ratio()
    score = max(keyword_score, (0.75 * keyword_score) + (0.25 * description_score))
    return ProfileMatch(profile=profile, score=round(min(1.0, score), 3))


def _keyword_score(text: str, keywords: list[str]) -> float:
    if not keywords:
        return 0.0
    scores = [_keyword_similarity(text, keyword) for keyword in keywords]
    best_score = max(scores)
    top_scores = sorted(scores, reverse=True)[:3]
    top_average = sum(top_scores) / len(top_scores)
    strong_match_bonus = min(0.12, 0.04 * sum(1 for score in scores if score >= 0.78))
    return min(1.0, (0.65 * best_score) + (0.35 * top_average) + strong_match_bonus)


def _keyword_similarity(text: str, keyword: str) -> float:
    if keyword in text:
        return 1.0
    tokens = text.split()
    keyword_token_count = len(keyword.split())
    candidates = list(tokens)
    if keyword_token_count > 1 and len(tokens) >= keyword_token_count:
        candidates.extend(
            " ".join(tokens[index : index + keyword_token_count])
            for index in range(0, len(tokens) - keyword_token_count + 1)
        )
    if not candidates:
        return 0.0
    return max(SequenceMatcher(None, keyword, candidate).ratio() for candidate in candidates)
