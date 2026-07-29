from __future__ import annotations

from aiogram import Bot

from config.settings import Settings
from services.ai_service import AISummaryResult
from services.conversation_service import ConversationSnapshot
from storage.models import LeadRecord
from storage.repository import Repository
from utils.helpers import html_escape, split_text, utc_now_iso


class LeadService:
    def __init__(self, repository: Repository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    async def upsert_lead_from_snapshot(
        self,
        chat_id: int,
        snapshot: ConversationSnapshot,
        ai_result: AISummaryResult | None = None,
        operator_note: str | None = None,
        status: str | None = None,
    ) -> LeadRecord:
        context = snapshot.context
        summary = ai_result.summary if ai_result else ""
        next_step = ai_result.recommended_next_step if ai_result else snapshot.current_question
        lead = LeadRecord(
            chat_id=chat_id,
            name=context.get("name"),
            phone=context.get("phone"),
            telegram=context.get("telegram"),
            region=context.get("region"),
            accident_date=context.get("accident_date"),
            source=context.get("source") or "telegram",
            situation_summary=context.get("situation"),
            stage=snapshot.stage,
            urgency=ai_result.priority if ai_result else snapshot.urgency,
            perspective=snapshot.perspective,
            documents=context.get("documents"),
            next_step=next_step,
            ai_comment=ai_result.comment if ai_result else "",
            status=status or ("handoff" if snapshot.handed_off else "new"),
            handed_off=snapshot.handed_off,
            operator_note=operator_note,
            summary=summary,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        await self.repository.save_lead(lead)
        return lead

    def format_lead_card(self, lead: LeadRecord) -> str:
        lines = [
            "<b>Новая карточка лида</b>",
            f"ID чата: <code>{lead.chat_id}</code>",
            f"Имя: {html_escape(lead.name or 'не указано')}",
            f"Телефон: {html_escape(lead.phone or 'не указан')}",
            f"Telegram: {html_escape(lead.telegram or 'не указан')}",
            f"Регион: {html_escape(lead.region or 'не указан')}",
            f"Дата ДТП: {html_escape(lead.accident_date or 'не указана')}",
            f"Стадия: {html_escape(lead.stage or 'не указана')}",
            f"Срочность: {html_escape(lead.urgency or 'не указана')}",
            f"Перспективность: {html_escape(lead.perspective or 'не указана')}",
            f"Статус: {html_escape(lead.status)}",
            "",
            f"<b>Ситуация:</b> {html_escape(lead.situation_summary or 'не указано')}",
            f"<b>Документы:</b> {html_escape(lead.documents or 'не указано')}",
            f"<b>Следующий шаг:</b> {html_escape(lead.next_step or 'не указан')}",
        ]
        if lead.summary:
            lines.extend(["", f"<b>Summary:</b> {html_escape(lead.summary)}"])
        if lead.ai_comment:
            lines.extend(["", f"<b>AI-комментарий:</b> {html_escape(lead.ai_comment)}"])
        if lead.operator_note:
            lines.extend(["", f"<b>Заметка оператора:</b> {html_escape(lead.operator_note)}"])
        return "\n".join(lines)

    async def notify_admins(self, bot: Bot, lead: LeadRecord) -> None:
        text = self.format_lead_card(lead)
        if self.settings.admin_chat_id:
            for chunk in split_text(text):
                await bot.send_message(self.settings.admin_chat_id, chunk)
        if self.settings.lead_channel_id:
            for chunk in split_text(text):
                await bot.send_message(self.settings.lead_channel_id, chunk)
