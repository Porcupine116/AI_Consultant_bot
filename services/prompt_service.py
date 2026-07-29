from __future__ import annotations

import json

from services.conversation_service import ConversationSnapshot


class PromptService:
    def build_consultation_messages(
        self,
        snapshot: ConversationSnapshot,
        recent_messages: list[dict[str, str]],
        user_message: str,
        tone: str,
        language: str,
    ) -> list[dict[str, str]]:
        system = f"""
Ты — AI-консультант по ДТП и страховым спорам.
Твоя задача — вести первичную консультацию естественно, спокойно и без лишней воды.
Не выдумывай факты. Если данных не хватает — задай ровно один короткий уточняющий вопрос.
Не используй тяжёлые юридические термины без необходимости.
Если ситуация сложная или человек просит человека — мягко предложи передать диалог специалисту.
Отвечай на языке: {language}.
Тон общения: {tone}.
Верни строго JSON без markdown и без пояснений по схеме:
{{
  "reply": "короткий ответ пользователю",
  "next_question": "один уточняющий вопрос или пустая строка",
  "needs_operator": true/false,
  "ask_contacts": true/false,
  "urgency": "low|medium|high",
  "perspective": "good|needs_review|unclear",
  "stage": "intake|qualification|contacts|ready_for_handoff|handoff",
  "summary": "короткое резюме обращения",
  "ai_comment": "служебная короткая заметка"
}}
""".strip()

        context_payload = {
            "snapshot": {
                "chat_id": snapshot.chat_id,
                "stage": snapshot.stage,
                "missing_fields": snapshot.missing_fields,
                "urgency": snapshot.urgency,
                "perspective": snapshot.perspective,
                "operator_requested": snapshot.operator_requested,
                "handed_off": snapshot.handed_off,
                "current_question": snapshot.current_question,
            },
            "known_context": snapshot.context,
            "recent_messages": recent_messages,
            "new_user_message": user_message,
        }

        user = f"Контекст диалога:\n{json.dumps(context_payload, ensure_ascii=False, indent=2)}"
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def build_summary_prompt(self, snapshot: ConversationSnapshot, recent_messages: list[dict[str, str]]) -> list[dict[str, str]]:
        system = """
Ты — помощник, который делает краткое резюме обращения для специалиста.
Верни строго JSON без markdown:
{
  "summary": "краткое резюме",
  "recommended_next_step": "следующий шаг",
  "priority": "low|medium|high",
  "comment": "короткий комментарий"
}
""".strip()
        user = json.dumps(
            {
                "snapshot": {
                    "stage": snapshot.stage,
                    "missing_fields": snapshot.missing_fields,
                    "urgency": snapshot.urgency,
                    "perspective": snapshot.perspective,
                    "context": snapshot.context,
                },
                "recent_messages": recent_messages,
            },
            ensure_ascii=False,
            indent=2,
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]
