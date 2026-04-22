"""Small utility helpers."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return a naive UTC timestamp for SQLite compatibility."""

    return datetime.now(timezone.utc).replace(tzinfo=None)


def utcnow_iso() -> str:
    """Return an ISO8601 UTC timestamp string."""

    return utcnow().isoformat(timespec="seconds") + "Z"


def dedupe_texts(items: list[str], limit: int | None = None) -> list[str]:
    """Dedupe while preserving order and dropping blanks."""

    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
        if limit is not None and len(output) >= limit:
            break
    return output

