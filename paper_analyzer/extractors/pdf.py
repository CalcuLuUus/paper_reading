"""PDF text extraction helpers."""

from __future__ import annotations

import fitz

from paper_analyzer.schemas import DocumentSection, PaperDocument


class PDFExtractionError(RuntimeError):
    """Raised when PDF extraction fails."""


def extract_pdf_document(
    pdf_bytes: bytes,
    *,
    source_hash: str,
    source_type: str,
    text_threshold: int,
    paper_id: str | None = None,
    title_hint: str | None = None,
) -> PaperDocument:
    """Extract text from a text-based PDF into a PaperDocument."""

    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # pragma: no cover - library exception types are broad
        raise PDFExtractionError("unable to open PDF") from exc

    page_texts: list[str] = []
    for page in document:
        text = page.get_text("text").strip()
        if text:
            page_texts.append(text)

    joined_text = "\n\n".join(page_texts).strip()
    if len(joined_text) < text_threshold:
        raise PDFExtractionError("PDF文本过少，疑似扫描版；v1 暂不支持 OCR")

    title = title_hint or _extract_pdf_title(joined_text)
    sections = [
        DocumentSection(heading=f"第 {index + 1} 页", content=text)
        for index, text in enumerate(page_texts)
        if text
    ]
    return PaperDocument(
        title=title,
        source_type="pdf",
        source_hash=source_hash,
        paper_id=paper_id,
        content=joined_text,
        sections=sections,
        metadata={"page_count": len(page_texts)},
    )


def _extract_pdf_title(text: str) -> str | None:
    first_block = text.split("\n\n", 1)[0]
    candidate = first_block.splitlines()[0].strip() if first_block else ""
    return candidate or None

