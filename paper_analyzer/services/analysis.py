"""LLM-driven paper analysis pipeline."""

from __future__ import annotations

import json

from paper_analyzer.clients.llm import OpenAICompatibleClient
from paper_analyzer.config import Settings
from paper_analyzer.schemas import ChunkEvidence, PaperAnalysisOutput, PaperDocument
from paper_analyzer.services.chunking import chunk_document
from paper_analyzer.services.prompts import (
    EVIDENCE_SYSTEM_PROMPT,
    FINAL_SYSTEM_PROMPT,
    build_evidence_prompt,
    build_final_prompt,
)
from paper_analyzer.utils import dedupe_texts


class PaperAnalyzer:
    """Two-stage analyzer: evidence extraction, then final synthesis."""

    def __init__(self, settings: Settings, llm_client: OpenAICompatibleClient):
        self.settings = settings
        self.llm_client = llm_client

    def analyze(self, document: PaperDocument) -> PaperAnalysisOutput:
        if not document.content.strip():
            raise ValueError("论文正文为空，无法分析")

        chunks = chunk_document(document, self.settings.llm_max_chunk_chars)
        evidence_chunks = [
            self._extract_chunk_evidence(document, chunk, index + 1, len(chunks))
            for index, chunk in enumerate(chunks)
        ]
        merged_evidence = self._merge_evidence(evidence_chunks)
        return self._finalize(document, merged_evidence)

    def _extract_chunk_evidence(
        self,
        document: PaperDocument,
        chunk: str,
        index: int,
        total: int,
    ) -> ChunkEvidence:
        prompt = build_evidence_prompt(document, chunk, index, total)
        result = self.llm_client.complete_json(
            schema=ChunkEvidence,
            system_prompt=EVIDENCE_SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0.1,
            max_tokens=2000,
            json_retries=1,
            transient_retries=2,
        )
        return ChunkEvidence.model_validate(result.model_dump())

    def _merge_evidence(self, evidence_chunks: list[ChunkEvidence]) -> ChunkEvidence:
        merged: dict[str, list[str]] = {field: [] for field in ChunkEvidence.model_fields}
        for chunk in evidence_chunks:
            for field in ChunkEvidence.model_fields:
                merged[field].extend(getattr(chunk, field))
        cleaned = {
            field: dedupe_texts(values, limit=12 if field in {"keywords", "domains"} else 20)
            for field, values in merged.items()
        }
        return ChunkEvidence.model_validate(cleaned)

    def _finalize(self, document: PaperDocument, evidence: ChunkEvidence) -> PaperAnalysisOutput:
        compact_evidence = evidence.model_dump()
        serialized = json.dumps(compact_evidence, ensure_ascii=False)
        if len(serialized) > self.settings.llm_max_evidence_chars:
            compact_evidence = {
                key: dedupe_texts(value, limit=8 if key in {"keywords", "domains"} else 12)
                for key, value in compact_evidence.items()
            }
            evidence = ChunkEvidence.model_validate(compact_evidence)

        prompt = build_final_prompt(document, evidence)
        result = self.llm_client.complete_json(
            schema=PaperAnalysisOutput,
            system_prompt=FINAL_SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0.2,
            max_tokens=4000,
            json_retries=1,
            transient_retries=2,
        )
        return PaperAnalysisOutput.model_validate(result.model_dump())

