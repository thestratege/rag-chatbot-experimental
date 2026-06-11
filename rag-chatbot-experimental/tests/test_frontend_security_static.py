from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_PATHS = [
    PROJECT_ROOT / "frontend" / "src",
    PROJECT_ROOT / "frontend" / "public",
    PROJECT_ROOT / "frontend" / ".env.local.example",
]


def _frontend_texts() -> dict[Path, str]:
    files: dict[Path, str] = {}
    for path in FRONTEND_PATHS:
        if path.is_file():
            files[path] = path.read_text(encoding="utf-8")
            continue
        for child in path.rglob("*"):
            if child.is_file() and child.suffix in {".ts", ".tsx", ".html", ".css"}:
                files[child] = child.read_text(encoding="utf-8")
    return files


def test_frontend_does_not_use_unsafe_html_rendering() -> None:
    for path, content in _frontend_texts().items():
        assert "dangerouslySetInnerHTML" not in content, f"Unsafe React HTML rendering in {path}"
        assert ".innerHTML" not in content, f"Direct innerHTML assignment in {path}"


def test_user_messages_stay_text_and_assistant_uses_sanitized_markdown() -> None:
    component = PROJECT_ROOT / "frontend" / "src" / "components" / "ChatMessage.tsx"
    content = component.read_text(encoding="utf-8")
    markdown_component = PROJECT_ROOT / "frontend" / "src" / "components" / "AssistantMarkdown.tsx"
    markdown_content = markdown_component.read_text(encoding="utf-8")

    assert "<p>{message.content}</p>" in content
    assert "<AssistantMarkdown" in content
    assert "rehypeSanitize" in markdown_content
    assert "skipHtml" in markdown_content
    assert "dangerouslySetInnerHTML" not in content
    assert "dangerouslySetInnerHTML" not in markdown_content


def test_frontend_sources_do_not_contain_backend_secrets_or_demo_tokens() -> None:
    forbidden_markers = {
        "OPENROUTER_API_KEY",
        "DEMO_AUTH_TOKEN",
        "DEMO_ADMIN_AUTH_TOKEN",
        "demo-token",
        "demo-admin-token",
    }

    for path, content in _frontend_texts().items():
        for marker in forbidden_markers:
            assert marker not in content, f"Forbidden front-end marker {marker} found in {path}"
