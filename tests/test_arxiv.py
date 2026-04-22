from paper_analyzer.extractors.arxiv import extract_arxiv_id


def test_extract_arxiv_id_from_common_formats():
    assert extract_arxiv_id("https://arxiv.org/abs/2401.01234") == "2401.01234"
    assert extract_arxiv_id("https://arxiv.org/pdf/2401.01234.pdf") == "2401.01234"
    assert extract_arxiv_id("arXiv:cs/0112017v1") == "cs/0112017v1"

