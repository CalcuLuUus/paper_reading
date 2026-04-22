"""Project-wide constants."""

from __future__ import annotations

TITLE_FIELD = "论文标题/备注"
PDF_FIELD = "PDF附件"
ARXIV_FIELD = "arXiv链接"

OUTPUT_ABSTRACT_TRANSLATION = "0_摘要翻译"
OUTPUT_MOTIVATION = "1_方法动机"
OUTPUT_METHOD_DESIGN = "2_方法设计"
OUTPUT_COMPARISON = "3_与其他方法对比"
OUTPUT_EXPERIMENT = "4_实验表现与优势"
OUTPUT_LEARNING = "5_学习与应用"
OUTPUT_SUMMARY = "6_总结"
OUTPUT_KEYWORDS = "7_关键词领域"

STATUS_FIELD = "分析状态"
ERROR_FIELD = "错误信息"
SOURCE_TYPE_FIELD = "来源类型"
SOURCE_HASH_FIELD = "来源哈希"
PAPER_ID_FIELD = "论文ID"
LAST_ANALYZED_AT_FIELD = "最后分析时间"

STATUS_QUEUED = "排队中"
STATUS_RUNNING = "分析中"
STATUS_COMPLETED = "已完成"
STATUS_FAILED = "失败"

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"

TRIGGER_FIELDS = {PDF_FIELD, ARXIV_FIELD}

OUTPUT_FIELD_MAP = {
    OUTPUT_ABSTRACT_TRANSLATION: "abstract_translation",
    OUTPUT_MOTIVATION: "motivation",
    OUTPUT_METHOD_DESIGN: "method_design",
    OUTPUT_COMPARISON: "comparison",
    OUTPUT_EXPERIMENT: "experimental_performance",
    OUTPUT_LEARNING: "learning_and_application",
    OUTPUT_SUMMARY: "summary",
    OUTPUT_KEYWORDS: "keywords_domain",
}

