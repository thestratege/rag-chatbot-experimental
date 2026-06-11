from app.conversation_manager import ConversationManager


def test_conversation_manager_creates_id_and_keeps_history() -> None:
    manager = ConversationManager(history_limit=2)
    conversation_id = manager.get_or_create()

    manager.append(conversation_id, role="user", content="Bonjour", intent="greeting")
    manager.append(conversation_id, role="assistant", content="Bonjour")

    history = manager.history(conversation_id)

    assert len(history) == 2
    assert history[0].role == "user"
    assert history[1].role == "assistant"


def test_conversation_manager_limits_history() -> None:
    manager = ConversationManager(history_limit=2)
    conversation_id = manager.get_or_create("demo")

    manager.append(conversation_id, role="user", content="un")
    manager.append(conversation_id, role="assistant", content="deux")
    manager.append(conversation_id, role="user", content="trois")

    history = manager.history(conversation_id)

    assert [message.content for message in history] == ["deux", "trois"]


def test_conversation_manager_resets_history() -> None:
    manager = ConversationManager(history_limit=10)
    conversation_id = manager.get_or_create("demo")
    manager.append(conversation_id, role="user", content="Bonjour")

    manager.reset(conversation_id)

    assert manager.history(conversation_id) == []
