from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.schemas import IntentName


@dataclass(frozen=True)
class ConversationMessage:
    role: str
    content: str
    timestamp: str
    intent: IntentName | None = None


class ConversationManager:
    """In-memory conversation history for the demo front office."""

    def __init__(self, history_limit: int = 10) -> None:
        if history_limit <= 0:
            raise ValueError("history_limit doit être supérieur à 0.")
        self.history_limit = history_limit
        self._histories: defaultdict[str, deque[ConversationMessage]] = defaultdict(
            lambda: deque(maxlen=self.history_limit)
        )

    def get_or_create(self, conversation_id: str | None = None) -> str:
        if conversation_id and conversation_id.strip():
            cleaned_id = conversation_id.strip()
            self._histories[cleaned_id]
            return cleaned_id
        new_id = str(uuid4())
        self._histories[new_id]
        return new_id

    def append(
        self,
        conversation_id: str,
        *,
        role: str,
        content: str,
        intent: IntentName | None = None,
    ) -> None:
        self._histories[conversation_id].append(
            ConversationMessage(
                role=role,
                content=content,
                intent=intent,
                timestamp=datetime.now(UTC).isoformat(),
            )
        )

    def history(self, conversation_id: str) -> list[ConversationMessage]:
        return list(self._histories.get(conversation_id, []))

    def reset(self, conversation_id: str) -> None:
        self._histories[conversation_id].clear()

    def exists(self, conversation_id: str) -> bool:
        return conversation_id in self._histories
