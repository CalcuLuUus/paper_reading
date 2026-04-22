"""Chunking utilities for long documents."""

from __future__ import annotations

from paper_analyzer.schemas import PaperDocument


def chunk_document(document: PaperDocument, max_chars: int) -> list[str]:
    """Chunk a paper into roughly bounded text slices."""

    if not document.sections:
        return _chunk_raw_text(document.content, max_chars)

    chunks: list[str] = []
    current = ""
    for section in document.sections:
        section_text = f"{section.heading}\n{section.content}".strip()
        if len(section_text) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(_chunk_raw_text(section_text, max_chars))
            continue
        if len(current) + len(section_text) + 2 <= max_chars:
            current = f"{current}\n\n{section_text}".strip()
        else:
            if current:
                chunks.append(current.strip())
            current = section_text
    if current:
        chunks.append(current.strip())
    return chunks or _chunk_raw_text(document.content, max_chars)


def _chunk_raw_text(text: str, max_chars: int) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            for start in range(0, len(paragraph), max_chars):
                chunks.append(paragraph[start : start + max_chars].strip())
            continue
        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}".strip()
        else:
            chunks.append(current.strip())
            current = paragraph
    if current:
        chunks.append(current.strip())
    return chunks

