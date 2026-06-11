from app.chunker import TextChunker
from app.schemas import DocumentPart


def test_chunker_creates_overlapping_chunks_with_metadata() -> None:
    text = (
        "Première phrase de test. Deuxième phrase avec une information utile. "
        "Troisième phrase qui force un découpage. Quatrième phrase de validation. "
        "Cinquième phrase pour vérifier le chevauchement."
    )
    document = DocumentPart(
        text=text,
        metadata={
            "file_name": "guide.txt",
            "source_path": "/tmp/guide.txt",
            "file_type": "txt",
            "page": None,
            "ingested_at": "2026-05-19T00:00:00Z",
        },
    )

    chunks = TextChunker(chunk_size=90, chunk_overlap=20).chunk_document(document)

    assert len(chunks) >= 2
    assert all(chunk.text for chunk in chunks)
    assert all(chunk.metadata["file_name"] == "guide.txt" for chunk in chunks)
    assert all("chunk_id" in chunk.metadata for chunk in chunks)


def test_chunker_handles_short_document() -> None:
    document = DocumentPart(
        text="Texte court avec une seule information.",
        metadata={"file_name": "note.md", "source_path": "/tmp/note.md", "file_type": "md", "page": None},
    )

    chunks = TextChunker(chunk_size=1000, chunk_overlap=100).chunk_document(document)

    assert len(chunks) == 1
    assert chunks[0].text == "Texte court avec une seule information."

