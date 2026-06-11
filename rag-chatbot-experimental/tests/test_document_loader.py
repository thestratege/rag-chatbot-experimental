from pathlib import Path

import pytest

from app.document_loader import DocumentLoader, DocumentLoadingError


class FakePdfPage:
    def __init__(self, text: str | None) -> None:
        self.text = text

    def extract_text(self) -> str | None:
        return self.text


class FakePdfReader:
    def __init__(self, pages: list[FakePdfPage]) -> None:
        self.pages = pages


def test_text_document_loading_still_works(tmp_path: Path) -> None:
    path = tmp_path / "note.txt"
    path.write_text("Information de test.", encoding="utf-8")

    parts = DocumentLoader(tmp_path).load_file(path)

    assert len(parts) == 1
    assert parts[0].text == "Information de test."
    assert parts[0].metadata["source_type"] == "txt"
    assert parts[0].metadata["source"] == str(path.resolve())
    assert parts[0].metadata["document_id"]
    assert parts[0].metadata["file_hash"]
    assert parts[0].metadata["last_modified"]
    assert parts[0].metadata["indexed_at"]
    assert parts[0].metadata["allowed_groups"] == ["public"]
    assert parts[0].metadata["section_title"] == "Information de test."


def test_pdf_loading_extracts_text_page_by_page_with_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "procedure.pdf"
    path.write_bytes(b"%PDF-test")
    reader = FakePdfReader([FakePdfPage("Première page."), FakePdfPage(""), FakePdfPage("Troisième page.")])
    monkeypatch.setattr("pypdf.PdfReader", lambda _: reader)

    parts = DocumentLoader(tmp_path).load_file(path)

    assert [part.metadata["page"] for part in parts] == [1, 3]
    assert all(part.metadata["file_name"] == "procedure.pdf" for part in parts)
    assert all(part.metadata["source_type"] == "pdf" for part in parts)
    assert all(part.metadata["source"] == str(path.resolve()) for part in parts)


def test_pdf_without_extractable_text_returns_clear_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-scan")
    monkeypatch.setattr("pypdf.PdfReader", lambda _: FakePdfReader([FakePdfPage(None), FakePdfPage("")]))

    with pytest.raises(DocumentLoadingError, match="probablement scanné"):
        DocumentLoader(tmp_path).load_file(path)
