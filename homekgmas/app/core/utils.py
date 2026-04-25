"""Small utility helpers used across the application."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Iterable


def utc_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    """Produce a simple filesystem-safe identifier."""

    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    return normalized.strip("-") or "task"


def contains_keywords(text: str, keywords: Iterable[str]) -> bool:
    """Return True when any keyword occurs in text."""

    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def sentence_case(text: str) -> str:
    """Normalize spacing and trailing punctuation for short text fragments."""

    cleaned = re.sub(r"\s+", " ", str(text).strip())
    if not cleaned:
        return ""
    if cleaned[-1] not in ".!?":
        cleaned = f"{cleaned}."
    return cleaned[0].upper() + cleaned[1:]


def first_sentence(text: str) -> str:
    """Return the first sentence-like fragment from a block of text."""

    normalized = sentence_case(text)
    if not normalized:
        return ""
    match = re.split(r"(?<=[.!?])\s+", normalized, maxsplit=1)
    return match[0]


def normalize_text_list(
    value: Any,
    *,
    max_items: int = 3,
    fallback: list[str] | None = None,
) -> list[str]:
    """Coerce a string or list-like value into a clean, deduplicated string list."""

    fallback = fallback or []
    raw_items: list[Any]
    if value is None:
        raw_items = []
    elif isinstance(value, str):
        raw_items = re.split(r"(?:[;\n]+|(?<=[.!?])\s+)", value)
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, dict)):
        raw_items = list(value)
    else:
        raw_items = [value]

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = first_sentence(item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        normalized.append(text)
        seen.add(key)
        if len(normalized) >= max_items:
            break

    return normalized or [sentence_case(item) for item in fallback if sentence_case(item)][:max_items]


def dedupe_preserve_order(items: Iterable[str], *, limit: int | None = None) -> list[str]:
    """Return unique strings while preserving order."""

    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = sentence_case(item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        output.append(text)
        seen.add(key)
        if limit is not None and len(output) >= limit:
            break
    return output
