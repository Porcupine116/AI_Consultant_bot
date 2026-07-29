from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from utils.helpers import extract_name, extract_phone_candidates, extract_username, normalize_whitespace


@dataclass(slots=True)
class ConversationSnapshot:
    chat_id: int
    stage: str
    context: dict[str, Any] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    urgency: str = "medium"
    perspective: str = "needs_review"
    operator_requested: bool = False
    handed_off: bool = False
    current_question: str = ""


class ConversationService:
    def extract_fields(self, text: str, context: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_whitespace(text)
        result: dict[str, Any] = {}

        phones = extract_phone_candidates(normalized)
        if phones:
            result["phone"] = phones[0]

        username = extract_username(normalized)
        if username:
            result["telegram"] = username

        name = extract_name(normalized)
        if name:
            result["name"] = name

        date = self._extract_date(normalized)
        if date:
            result["accident_date"] = date

        region = self._extract_region(normalized)
        if region:
            result["region"] = region

        docs = self._extract_documents(normalized)
        if docs:
            result["documents"] = ", ".join(docs)

        insurance = self._detect_insurance(normalized)
        if insurance:
            result["insurance"] = insurance

        damage = self._detect_damage(normalized)
        if damage:
            result["damage"] = damage

        participants = self._detect_participants(normalized)
        if participants:
            result["participants"] = participants

        result["situation"] = context.get("situation") or self._extract_situation(normalized)
        result["source"] = context.get("source") or "telegram"

        return result

    def build_snapshot(self, chat_id: int, context: dict[str, Any], operator_requested: bool, handed_off: bool) -> ConversationSnapshot:
        missing = self._missing_fields(context)
        urgency = self._estimate_urgency(context)
        perspective = self._estimate_perspective(context, missing)
        question = self._next_question(context, missing)
        stage = self._stage_from_context(context, missing)
        return ConversationSnapshot(
            chat_id=chat_id,
            stage=stage,
            context=context,
            missing_fields=missing,
            urgency=urgency,
            perspective=perspective,
            operator_requested=operator_requested,
            handed_off=handed_off,
            current_question=question,
        )

    def _missing_fields(self, context: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        if not context.get("situation"):
            missing.append("situation")
        if not context.get("accident_date"):
            missing.append("accident_date")
        if not context.get("region"):
            missing.append("region")
        if not context.get("insurance"):
            missing.append("insurance")
        if not context.get("documents"):
            missing.append("documents")
        if not context.get("damage"):
            missing.append("damage")
        if not (context.get("name") or context.get("phone") or context.get("telegram")):
            missing.append("contacts")
        return missing

    def _stage_from_context(self, context: dict[str, Any], missing: list[str]) -> str:
        if context.get("handed_off"):
            return "handoff"
        if "situation" in missing or "accident_date" in missing:
            return "intake"
        if any(key in missing for key in ("insurance", "documents", "damage")):
            return "qualification"
        if "contacts" in missing:
            return "contacts"
        return "ready_for_handoff"

    def _next_question(self, context: dict[str, Any], missing: list[str]) -> str:
        if "situation" in missing:
            return "Кратко расскажите, что произошло."
        if "accident_date" in missing:
            return "Когда произошло ДТП?"
        if "region" in missing:
            return "В каком регионе или городе это было?"
        if "insurance" in missing:
            return "Есть ОСАГО у вас и у второй стороны?"
        if "documents" in missing:
            return "Какие документы уже есть на руках: европротокол, справка, постановление, фото?"
        if "damage" in missing:
            return "Что именно повреждено и есть ли скрытые повреждения?"
        if "contacts" in missing:
            return "Оставьте, пожалуйста, имя и телефон — тогда специалист сможет связаться с вами."
        return "Если хотите, я могу передать ситуацию специалисту и собрать итог по делу."

    def _estimate_urgency(self, context: dict[str, Any]) -> str:
        blob = " ".join(str(context.get(k, "")) for k in context.keys()).lower()
        urgent_markers = ["срочно", "сегодня", "завтра", "суд", "отказ", "иск", "срок", "пропуск", "скрыт", "не плат", "мало выплат"]
        if any(marker in blob for marker in urgent_markers):
            return "high"
        if any(word in blob for word in ("дтп", "осаго", "выплата")):
            return "medium"
        return "low"

    def _estimate_perspective(self, context: dict[str, Any], missing: list[str]) -> str:
        if context.get("damage") and context.get("documents") and context.get("insurance"):
            return "good"
        if len(missing) >= 4:
            return "unclear"
        return "needs_review"

    def _extract_situation(self, text: str) -> str:
        lowered = text.lower()
        if any(word in lowered for word in ("дтп", "авар", "столкнов", "удар", "врез")):
            return "ДТП / авария"
        if any(word in lowered for word in ("страхов", "осаго", "выплат")):
            return "Страховой спор"
        if any(word in lowered for word in ("суд", "иск", "претенз")):
            return "Судебный спор"
        return "Первичное обращение"

    def _extract_date(self, text: str) -> str | None:
        patterns = [
            r"(?:\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b)",
            r"(?:\b\d{1,2}\s+[а-яё]+\s+\d{4}\s*г?\.?\b)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        for key in ["сегодня", "вчера", "позавчера", "неделю назад", "месяц назад"]:
            if key in text.lower():
                return key
        return None

    def _extract_region(self, text: str) -> str | None:
        match = re.search(r"(?:из|в)\s+([А-ЯA-ZЁ][\w\-]+(?:\s+[А-ЯA-ZЁ][\w\-]+){0,2})", text)
        if match:
            region = match.group(1).strip()
            if len(region) >= 3:
                return region
        return None

    def _extract_documents(self, text: str) -> list[str]:
        docs = []
        lower = text.lower()
        variants = {
            "европротокол": "европротокол",
            "протокол": "протокол",
            "постановление": "постановление",
            "справка": "справка",
            "фото": "фото",
            "видео": "видео",
            "осмотр": "акт осмотра",
            "экспертиза": "экспертиза",
            "страховая": "обращение в страховую",
        }
        for key, label in variants.items():
            if key in lower:
                docs.append(label)
        return docs

    def _detect_insurance(self, text: str) -> str | None:
        lower = text.lower()
        if "осаго" in lower or "каско" in lower:
            return "Есть ОСАГО/КАСКО"
        if any(phrase in lower for phrase in ("нет страховки", "без осаго", "нет осаго")):
            return "Нет ОСАГО"
        return None

    def _detect_damage(self, text: str) -> str | None:
        lower = text.lower()
        if any(word in lower for word in ("скрыт", "капот", "бампер", "двер", "крыл", "стекл", "фара", "радиатор")):
            return "Есть описание повреждений"
        if any(word in lower for word in ("тотал", "сильн", "разбит", "не едет")):
            return "Сильные повреждения"
        return None

    def _detect_participants(self, text: str) -> str | None:
        lower = text.lower()
        if any(word in lower for word in ("я винов", "виноват", "по моей вине")):
            return "Пользователь считает себя виновным"
        if any(word in lower for word in ("не винов", "вина не моя", "другой винов")):
            return "Пользователь считает себя невиновным"
        return None
