"""Prompt templates for evidence extraction and final synthesis."""

from __future__ import annotations

import json

from paper_analyzer.schemas import ChunkEvidence, PaperDocument


EVIDENCE_SYSTEM_PROMPT = """你是一名严谨的科研论文分析助手。
你的任务是从给定论文片段中抽取“可核对的证据点”，用于后续汇总。
规则：
1. 只能依据提供的论文内容，不要补充外部常识。
2. 返回单个 JSON 对象，不要输出代码块。
3. 每个数组元素都用简洁中文表述，尽量保留原论文里的数字、数据集名、模块名。
4. 如果某字段没有信息，返回空数组。
JSON 字段固定为：
abstract_facts, motivation, limitations, hypothesis, pipeline, modules, formulas, comparisons, experiments, results, open_source, implementation, transferability, domains, keywords
"""


FINAL_SYSTEM_PROMPT = """你是一名面向文献管理场景的论文分析助手。
你会根据抽取好的证据，生成 8 个中文字段，字段固定如下：
abstract_translation, motivation, method_design, comparison, experimental_performance, learning_and_application, summary, keywords_domain

硬性要求：
1. 只返回单个 JSON 对象，不要输出代码块。
2. 所有内容必须是中文。
3. comparison 字段里必须包含一个 Markdown 表格。
4. keywords_domain 字段格式固定：
领域: ...
关键词: tag1; tag2; tag3
最多 10 个关键词。
5. summary 字段必须包含：
   a) 核心思想（≤20字）
   b) 速记版 Pipeline（3-5 步）
6. 如果证据不足，要明确写“论文未明确说明”，不要编造。"""


def build_evidence_prompt(document: PaperDocument, chunk: str, index: int, total: int) -> str:
    return (
        f"论文标题：{document.title or '未提供'}\n"
        f"来源类型：{document.source_type}\n"
        f"块序号：{index}/{total}\n\n"
        "请从下面的论文内容中提取证据 JSON：\n"
        f"{chunk}"
    )


def build_final_prompt(document: PaperDocument, evidence: ChunkEvidence) -> str:
    evidence_json = json.dumps(evidence.model_dump(), ensure_ascii=False, indent=2)
    return (
        f"论文标题：{document.title or '未提供'}\n"
        f"论文ID：{document.paper_id or '未提供'}\n\n"
        "下面是从论文全文抽取并汇总后的证据 JSON，请基于这些证据生成最终 8 个字段：\n"
        f"{evidence_json}"
    )

