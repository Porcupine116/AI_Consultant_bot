from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from config.settings import Settings

logger = logging.getLogger(__name__)


class AIServiceError(RuntimeError):
    pass


@dataclass(slots=True)
class AIConsultationResult:
    reply: str
    next_question: str = ""
    needs_operator: bool = False
    ask_contacts: bool = False
    urgency: str = "medium"
    perspective: str = "needs_review"
    stage: str = "intake"
    summary: str = ""
    ai_comment: str = ""
    raw_text: str = ""


@dataclass(slots=True)
class AISummaryResult:
    summary: str
    recommended_next_step: str = ""
    priority: str = "medium"
    comment: str = ""
    raw_text: str = ""


class AIService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.openrouter_base_url.rstrip("/"),
            timeout=httpx.Timeout(settings.request_timeout),
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
                "X-Title": settings.app_name,
            },
            trust_env=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat_consultation(self, messages: list[dict[str, str]]) -> AIConsultationResult:
        payload = {
            "model": self.settings.openrouter_model,
            "messages": messages,
            "temperature": self.settings.ai_temperature,
            "max_tokens": self.settings.ai_max_output_tokens,
        }
        raw = await self._post_json(payload)
        text = self._extract_content(raw)
        parsed = self._parse_json(text)
        if parsed:
            return AIConsultationResult(
                reply=str(parsed.get("reply") or parsed.get("message") or "").strip(),
                next_question=str(parsed.get("next_question") or "").strip(),
                needs_operator=bool(parsed.get("needs_operator", False)),
                ask_contacts=bool(parsed.get("ask_contacts", False)),
                urgency=str(parsed.get("urgency") or "medium").strip(),
                perspective=str(parsed.get("perspective") or "needs_review").strip(),
                stage=str(parsed.get("stage") or "intake").strip(),
                summary=str(parsed.get("summary") or "").strip(),
                ai_comment=str(parsed.get("ai_comment") or "").strip(),
                raw_text=text,
            )
        return AIConsultationResult(reply=text.strip(), raw_text=text)

    async def chat_summary(self, messages: list[dict[str, str]]) -> AISummaryResult:
        payload = {
            "model": self.settings.openrouter_model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 400,
        }
        raw = await self._post_json(payload)
        text = self._extract_content(raw)
        parsed = self._parse_json(text)
        if parsed:
            return AISummaryResult(
                summary=str(parsed.get("summary") or "").strip(),
                recommended_next_step=str(parsed.get("recommended_next_step") or "").strip(),
                priority=str(parsed.get("priority") or "medium").strip(),
                comment=str(parsed.get("comment") or "").strip(),
                raw_text=text,
            )
        return AISummaryResult(summary=text.strip(), raw_text=text)

    async def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.settings.request_retries + 1):
            try:
                response = await self._client.post("/chat/completions", json=payload)
                if response.status_code >= 400:
                    logger.error("OpenRouter HTTP %s: %s", response.status_code, response.text[:500])
                    response.raise_for_status()
                return response.json()
            except Exception as exc:
                last_error = exc
                logger.exception("OpenRouter attempt %s failed", attempt)
                if attempt < self.settings.request_retries:
                    await asyncio.sleep(min(2 * attempt, 5))
        raise AIServiceError("Не удалось получить ответ от AI") from last_error

    @staticmethod
    def _extract_content(raw: dict[str, Any]) -> str:
        try:
            return raw["choices"][0]["message"]["content"] or ""
        except Exception as exc:
            raise AIServiceError(f"Некорректный ответ AI: {raw!r}") from exc

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any] | None:
        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.IGNORECASE | re.DOTALL).strip()
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
