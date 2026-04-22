"""Helpers for fetching and parsing arXiv papers."""

from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

from paper_analyzer.schemas import DocumentSection, PaperDocument


class ArxivError(RuntimeError):
    """Raised when arXiv content cannot be fetched or parsed."""


NEW_STYLE_ARXIV = re.compile(r"(?P<id>\d{4}\.\d{4,5}(?:v\d+)?)")
OLD_STYLE_ARXIV = re.compile(r"(?P<id>[a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)", re.IGNORECASE)


def extract_arxiv_id(value: str | None) -> str | None:
    """Extract an arXiv identifier from a user-provided string."""

    if not value:
        return None
    text = value.strip()
    for pattern in (NEW_STYLE_ARXIV, OLD_STYLE_ARXIV):
        match = pattern.search(text)
        if match:
            return match.group("id")
    return None


def arxiv_abs_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/abs/{arxiv_id}"


def arxiv_html_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/html/{arxiv_id}"


def arxiv_pdf_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/pdf/{arxiv_id}.pdf"


class ArxivClient:
    """Fetch and parse arXiv HTML/PDF content."""

    def __init__(self, timeout_seconds: int = 120):
        self.timeout = httpx.Timeout(timeout_seconds)

    def fetch_html_document(self, arxiv_id: str, source_hash: str) -> PaperDocument:
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(arxiv_html_url(arxiv_id))
            response.raise_for_status()

        sections, title = parse_arxiv_html(response.text)
        if not sections:
            raise ArxivError(f"unable to parse arXiv HTML for {arxiv_id}")

        content = "\n\n".join(f"{section.heading}\n{section.content}" for section in sections)
        return PaperDocument(
            title=title,
            source_type="arxiv",
            source_hash=source_hash,
            paper_id=arxiv_id,
            content=content,
            sections=sections,
            metadata={"arxiv_url": arxiv_abs_url(arxiv_id)},
        )

    def fetch_pdf_bytes(self, arxiv_id: str) -> bytes:
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(arxiv_pdf_url(arxiv_id))
            response.raise_for_status()
            return response.content


def parse_arxiv_html(html_text: str) -> tuple[list[DocumentSection], str | None]:
    """Convert arXiv HTML to normalized sections."""

    soup = BeautifulSoup(html_text, "html.parser")
    title = None
    if soup.title and soup.title.text:
        title = soup.title.text.replace("arXiv.org", "").strip(" -")

    for node in soup(["script", "style", "noscript"]):
        node.decompose()

    root = soup.find("article") or soup.body
    if root is None:
        return [], title

    sections: list[DocumentSection] = []
    current_heading = "引言"
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines
        content = "\n".join(line for line in current_lines if line.strip()).strip()
        if content:
            sections.append(DocumentSection(heading=current_heading, content=content))
        current_lines = []

    for element in root.find_all(["h1", "h2", "h3", "h4", "p", "li"], recursive=True):
        text = " ".join(element.get_text(" ", strip=True).split())
        if not text:
            continue
        if element.name.startswith("h"):
            flush()
            current_heading = text
            continue
        current_lines.append(text)

    flush()
    return sections, title

