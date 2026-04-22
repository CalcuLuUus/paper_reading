from paper_analyzer.schemas import PaperAnalysisOutput


def test_paper_analysis_output_accepts_required_formats():
    output = PaperAnalysisOutput(
        abstract_translation="中文摘要",
        motivation="动机",
        method_design="设计",
        comparison="对比\n\n| 方法 | 优点 |\n| --- | --- |\n| Ours | 更强 |",
        experimental_performance="结果",
        learning_and_application="应用",
        summary="a) 核心思想：提升鲁棒性\nb) 速记版 Pipeline：1. 编码 2. 融合 3. 预测",
        keywords_domain="领域: 计算机视觉\n关键词: 鲁棒性; 检测; 迁移学习",
    )

    assert output.to_feishu_fields()["7_关键词领域"].startswith("领域:")


def test_paper_analysis_output_requires_markdown_table():
    try:
        PaperAnalysisOutput(
            abstract_translation="中文摘要",
            motivation="动机",
            method_design="设计",
            comparison="没有表格",
            experimental_performance="结果",
            learning_and_application="应用",
            summary="总结",
            keywords_domain="领域: NLP\n关键词: 检索",
        )
    except ValueError as exc:
        assert "markdown table" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected validation error")

