from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

TELEGRAM_LIMIT = 3900


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_whitespace(text: str) -> str:
    return re.sub(r"[ \t\f\v]+", " ", text).strip()


def normalize_phone(text: str) -> str | None:
    digits = re.sub(r"\D+", "", text)
    if len(digits) < 10:
        return None
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    return "+" + digits


def extract_phone_candidates(text: str) -> list[str]:
    candidates = re.findall(r"(\+?\d[\d\s\-()]{8,}\d)", text)
    phones: list[str] = []
    for candidate in candidates:
        phone = normalize_phone(candidate)
        if phone and phone not in phones:
            phones.append(phone)
    return phones


def extract_username(text: str) -> str | None:
    match = re.search(r"@([A-Za-z0-9_]{5,32})", text)
    if match:
        return "@" + match.group(1)
    return None


def extract_name(text: str) -> str | None:
    patterns = [
        r"(?:меня зовут|я)\s+([А-ЯA-ZЁ][а-яa-zё\-]+(?:\s+[А-ЯA-ZЁ][а-яa-zё\-]+){0,2})",
        r"^([А-ЯA-ZЁ][а-яa-zё\-]+(?:\s+[А-ЯA-ZЁ][а-яa-zё\-]+){0,2})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            return normalize_whitespace(match.group(1))
    return None


def split_text(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    clean = text.strip()
    if len(clean) <= limit:
        return [clean]

    chunks: list[str] = []
    while clean:
        if len(clean) <= limit:
            chunks.append(clean)
            break
        cut = clean.rfind("\n\n", 0, limit)
        if cut < limit * 0.4:
            cut = clean.rfind("\n", 0, limit)
        if cut < limit * 0.3:
            cut = clean.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        chunk = clean[:cut].rstrip()
        if not chunk:
            chunk = clean[:limit].rstrip()
            cut = limit
        chunks.append(chunk)
        clean = clean[cut:].lstrip()
    return chunks


def html_escape(text: str) -> str:
    return html.escape(text, quote=False)


def compact_lines(lines: Iterable[str]) -> str:
    filtered = [line.strip() for line in lines if line and line.strip()]
    return "\n".join(filtered)


def join_non_empty(values: Sequence[str | None], sep: str = ", ") -> str:
    return sep.join(v for v in values if v)
