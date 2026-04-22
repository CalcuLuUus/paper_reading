"""Pydantic schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from paper_analyzer.constants import (
    OUTPUT_ABSTRACT_TRANSLATION,
    OUTPUT_COMPARISON,
    OUTPUT_EXPERIMENT,
    OUTPUT_KEYWORDS,
    OUTPUT_LEARNING,
    OUTPUT_METHOD_DESIGN,
    OUTPUT_MOTIVATION,
    OUTPUT_SUMMARY,
)


class WebhookPayload(BaseModel):
    """Expected payload from Feishu automation HTTP action."""

    base_token: str
    table_id: str
    record_id: str
    changed_fields: list[str] = Field(default_factory=list)
    secret: str


class AttachmentFile(BaseModel):
    """Minimal representation of an attached Feishu file."""

    file_token: str
    name: str | None = None
    size: int | None = None


class SourceSelection(BaseModel):
    """Chosen source and fallbacks for a record."""

    source_type: Literal["arxiv", "pdf"]
    source_hash: str
    paper_id: str | None = None
    arxiv_id: str | None = None
    attachment_file_token: str | None = None
    attachment_name: str | None = None
    fallback_attachment_file_token: str | None = None
    fallback_attachment_name: str | None = None


class DocumentSection(BaseModel):
    """Paper section content."""

    heading: str
    content: str


class PaperDocument(BaseModel):
    """Normalized paper document for the analyzer."""

    title: str | None = None
    source_type: Literal["arxiv", "pdf"]
    source_hash: str
    paper_id: str | None = None
    content: str
    sections: list[DocumentSection] = Field(default_factory=list)
    metadata: dict[str, str | int | float | None] = Field(default_factory=dict)


class ChunkEvidence(BaseModel):
    """Evidence extracted from one text chunk."""

    abstract_facts: list[str] = Field(default_factory=list)
    motivation: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    hypothesis: list[str] = Field(default_factory=list)
    pipeline: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    formulas: list[str] = Field(default_factory=list)
    comparisons: list[str] = Field(default_factory=list)
    experiments: list[str] = Field(default_factory=list)
    results: list[str] = Field(default_factory=list)
    open_source: list[str] = Field(default_factory=list)
    implementation: list[str] = Field(default_factory=list)
    transferability: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class PaperAnalysisOutput(BaseModel):
    """Validated final per-column output."""

    abstract_translation: str = Field(alias=OUTPUT_ABSTRACT_TRANSLATION)
    motivation: str = Field(alias=OUTPUT_MOTIVATION)
    method_design: str = Field(alias=OUTPUT_METHOD_DESIGN)
    comparison: str = Field(alias=OUTPUT_COMPARISON)
    experimental_performance: str = Field(alias=OUTPUT_EXPERIMENT)
    learning_and_application: str = Field(alias=OUTPUT_LEARNING)
    summary: str = Field(alias=OUTPUT_SUMMARY)
    keywords_domain: str = Field(alias=OUTPUT_KEYWORDS)

    model_config = {"populate_by_name": True}

    @field_validator("comparison")
    @classmethod
    def ensure_markdown_table(cls, value: str) -> str:
        if "|" not in value:
            raise ValueError("comparison must include a markdown table")
        return value.strip()

    @field_validator("keywords_domain")
    @classmethod
    def ensure_keywords_format(cls, value: str) -> str:
        text = value.strip()
        if not text.startswith("领域:") or "关键词:" not in text:
            raise ValueError("keywords_domain must contain '领域:' and '关键词:'")
        return text

    def to_feishu_fields(self) -> dict[str, str]:
        return {
            OUTPUT_ABSTRACT_TRANSLATION: self.abstract_translation.strip(),
            OUTPUT_MOTIVATION: self.motivation.strip(),
            OUTPUT_METHOD_DESIGN: self.method_design.strip(),
            OUTPUT_COMPARISON: self.comparison.strip(),
            OUTPUT_EXPERIMENT: self.experimental_performance.strip(),
            OUTPUT_LEARNING: self.learning_and_application.strip(),
            OUTPUT_SUMMARY: self.summary.strip(),
            OUTPUT_KEYWORDS: self.keywords_domain.strip(),
        }
