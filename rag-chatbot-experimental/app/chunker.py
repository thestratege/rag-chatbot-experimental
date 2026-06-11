from __future__ import annotations

import hashlib
import re
from typing import Iterable

from app.schemas import DocumentChunk, DocumentPart


SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;:])\s+")


class TextChunker:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 150) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size doit être supérieur à 0.")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap doit être positif et inférieur à chunk_size.")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_documents(self, documents: Iterable[DocumentPart]) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        for document in documents:
            chunks.extend(self.chunk_document(document))
        return chunks

    def chunk_document(self, document: DocumentPart) -> list[DocumentChunk]:
        units = self._split_into_units(document.text)
        chunks_text = self._pack_units(units)
        result: list[DocumentChunk] = []
        for index, chunk_text in enumerate(chunks_text, start=1):
            chunk_id = self._build_chunk_id(document.metadata, index, chunk_text)
            result.append(
                DocumentChunk(
                    text=chunk_text,
                    metadata={
                        **document.metadata,
                        "chunk_index": index,
                        "chunk_id": chunk_id,
                    },
                )
            )
        return result

    def _split_into_units(self, text: str) -> list[str]:
        paragraphs = [paragraph.strip() for paragraph in re.split(r"\n{2,}", text) if paragraph.strip()]
        units: list[str] = []
        for paragraph in paragraphs:
            if len(paragraph) <= self.chunk_size:
                units.append(paragraph)
                continue
            sentences = [sentence.strip() for sentence in SENTENCE_BOUNDARY.split(paragraph) if sentence.strip()]
            for sentence in sentences:
                if len(sentence) <= self.chunk_size:
                    units.append(sentence)
                else:
                    units.extend(self._split_long_text(sentence))
        return units

    def _split_long_text(self, text: str) -> list[str]:
        words = text.split()
        parts: list[str] = []
        current: list[str] = []
        current_length = 0
        for word in words:
            added_length = len(word) + (1 if current else 0)
            if current and current_length + added_length > self.chunk_size:
                parts.append(" ".join(current))
                current = [word]
                current_length = len(word)
            else:
                current.append(word)
                current_length += added_length
        if current:
            parts.append(" ".join(current))
        return parts

    def _pack_units(self, units: list[str]) -> list[str]:
        chunks: list[str] = []
        current = ""
        for unit in units:
            separator = "\n\n" if current else ""
            candidate = f"{current}{separator}{unit}" if current else unit
            if current and len(candidate) > self.chunk_size:
                chunks.append(current.strip())
                overlap = self._build_overlap(current)
                current = f"{overlap}\n\n{unit}".strip() if overlap else unit
                if len(current) > self.chunk_size:
                    chunks.extend(self._split_long_text(current))
                    current = ""
            else:
                current = candidate
        if current.strip():
            chunks.append(current.strip())
        return chunks

    def _build_overlap(self, text: str) -> str:
        if self.chunk_overlap == 0 or len(text) <= self.chunk_overlap:
            return ""
        overlap = text[-self.chunk_overlap :]
        boundary = max(overlap.find(". "), overlap.find("\n"))
        if boundary > 0:
            overlap = overlap[boundary + 1 :]
        return overlap.strip()

    def _build_chunk_id(self, metadata: dict[str, object], index: int, text: str) -> str:
        source = metadata.get("source_path", metadata.get("file_name", "document"))
        page = metadata.get("page", "")
        digest = hashlib.sha1(f"{source}:{page}:{index}:{text[:200]}".encode("utf-8")).hexdigest()[:12]
        return f"{PathSafe.stem(str(metadata.get('file_name', 'document')))}-p{page or 'na'}-c{index}-{digest}"


class PathSafe:
    @staticmethod
    def stem(file_name: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", file_name.rsplit(".", 1)[0]).strip("-") or "document"

