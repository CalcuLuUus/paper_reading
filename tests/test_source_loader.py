from paper_analyzer.constants import ARXIV_FIELD, PDF_FIELD
from paper_analyzer.services.source_loader import resolve_source_selection


def test_source_selection_prefers_arxiv_and_keeps_pdf_fallback():
    selection = resolve_source_selection(
        {
            ARXIV_FIELD: "https://arxiv.org/abs/2401.01234",
            PDF_FIELD: [{"file_token": "boxcn123", "name": "paper.pdf"}],
        }
    )

    assert selection.source_type == "arxiv"
    assert selection.source_hash == "arxiv:2401.01234"
    assert selection.fallback_attachment_file_token == "boxcn123"


def test_source_selection_uses_pdf_when_no_arxiv():
    selection = resolve_source_selection(
        {
            PDF_FIELD: [{"file_token": "boxcn123", "name": "paper.pdf"}],
        }
    )

    assert selection.source_type == "pdf"
    assert selection.source_hash == "pdf:boxcn123"

