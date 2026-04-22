"""Resolve and load paper sources from record fields."""

from __future__ import annotations

from typing import Any

from paper_analyzer.clients.feishu import FeishuClient
from paper_analyzer.config import Settings
from paper_analyzer.constants import ARXIV_FIELD, PDF_FIELD
from paper_analyzer.extractors.arxiv import ArxivClient, ArxivError, extract_arxiv_id
from paper_analyzer.extractors.pdf import PDFExtractionError, extract_pdf_document
from paper_analyzer.schemas import AttachmentFile, PaperDocument, SourceSelection


class SourceSelectionError(ValueError):
    """Raised when a record does not contain a valid source."""


def resolve_source_selection(fields: dict[str, Any]) -> SourceSelection:
    """Resolve the current record fields into a primary source and fallbacks."""

    arxiv_id = extract_arxiv_id(_string_value(fields.get(ARXIV_FIELD)))
    attachment = _first_attachment(fields.get(PDF_FIELD))

    if arxiv_id:
        return SourceSelection(
            source_type="arxiv",
            source_hash=f"arxiv:{arxiv_id}",
            paper_id=arxiv_id,
            arxiv_id=arxiv_id,
            fallback_attachment_file_token=attachment.file_token if attachment else None,
            fallback_attachment_name=attachment.name if attachment else None,
        )
    if attachment:
        return SourceSelection(
            source_type="pdf",
            source_hash=f"pdf:{attachment.file_token}",
            attachment_file_token=attachment.file_token,
            attachment_name=attachment.name,
        )
    raise SourceSelectionError("未检测到可分析输入：请提供 arXiv 链接或 PDF 附件")


class PaperSourceLoader:
    """Load a normalized PaperDocument from Feishu or arXiv."""

    def __init__(self, settings: Settings, feishu_client: FeishuClient):
        self.settings = settings
        self.feishu_client = feishu_client
        self.arxiv_client = ArxivClient(timeout_seconds=settings.llm_request_timeout_sec)

    def load(self, selection: SourceSelection, title_hint: str | None = None) -> PaperDocument:
        if selection.source_type == "arxiv":
            return self._load_arxiv_first(selection, title_hint=title_hint)
        if not selection.attachment_file_token:
            raise SourceSelectionError("PDF 来源缺少 file_token")
        return self._load_attachment_pdf(
            selection.attachment_file_token,
            selection.source_hash,
            title_hint=title_hint or selection.attachment_name,
            paper_id=selection.paper_id,
        )

    def _load_arxiv_first(self, selection: SourceSelection, title_hint: str | None) -> PaperDocument:
        if not selection.arxiv_id:
            raise SourceSelectionError("arXiv 来源缺少 arXiv ID")
        try:
            return self.arxiv_client.fetch_html_document(selection.arxiv_id, selection.source_hash)
        except Exception:
            try:
                pdf_bytes = self.arxiv_client.fetch_pdf_bytes(selection.arxiv_id)
                return extract_pdf_document(
                    pdf_bytes,
                    source_hash=selection.source_hash,
                    source_type="arxiv",
                    text_threshold=self.settings.pdf_text_threshold,
                    paper_id=selection.paper_id,
                    title_hint=title_hint,
                )
            except Exception as arxiv_pdf_exc:
                if selection.fallback_attachment_file_token:
                    return self._load_attachment_pdf(
                        selection.fallback_attachment_file_token,
                        selection.source_hash,
                        title_hint=title_hint or selection.fallback_attachment_name,
                        paper_id=selection.paper_id,
                    )
                raise ArxivError(str(arxiv_pdf_exc)) from arxiv_pdf_exc

    def _load_attachment_pdf(
        self,
        file_token: str,
        source_hash: str,
        *,
        title_hint: str | None,
        paper_id: str | None,
    ) -> PaperDocument:
        pdf_bytes = self.feishu_client.download_attachment(file_token)
        max_bytes = self.settings.max_pdf_mb * 1024 * 1024
        if len(pdf_bytes) > max_bytes:
            raise PDFExtractionError(f"PDF 超过大小限制：>{self.settings.max_pdf_mb} MB")
        return extract_pdf_document(
            pdf_bytes,
            source_hash=source_hash,
            source_type="pdf",
            text_threshold=self.settings.pdf_text_threshold,
            paper_id=paper_id,
            title_hint=title_hint,
        )


def _string_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _first_attachment(value: Any) -> AttachmentFile | None:
    if not value:
        return None
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and item.get("file_token"):
                return AttachmentFile.model_validate(item)
    return None

