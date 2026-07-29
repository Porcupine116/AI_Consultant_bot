from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class UserRecord:
    chat_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None


@dataclass(slots=True)
class ConversationRecord:
    chat_id: int
    state: str | None = None
    stage: str | None = None
    handed_off: bool = False
    operator_requested: bool = False
    context: dict[str, Any] = field(default_factory=dict)
    last_ai_reply: str | None = None


@dataclass(slots=True)
class MessageRecord:
    role: str
    content: str
    created_at: str


@dataclass(slots=True)
class LeadRecord:
    chat_id: int
    name: str | None = None
    phone: str | None = None
    telegram: str | None = None
    region: str | None = None
    accident_date: str | None = None
    source: str | None = None
    situation_summary: str | None = None
    stage: str | None = None
    urgency: str | None = None
    perspective: str | None = None
    documents: str | None = None
    next_step: str | None = None
    ai_comment: str | None = None
    status: str = "new"
    handed_off: bool = False
    operator_note: str | None = None
    summary: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
