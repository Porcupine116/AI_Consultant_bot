from __future__ import annotations

from storage.models import MessageRecord
from utils.helpers import html_escape


def format_recent_history(messages: list[MessageRecord]) -> str:
    lines = ["<b>Последние сообщения</b>"]
    if not messages:
        lines.append("История пока пуста.")
        return "\n".join(lines)
    for message in messages:
        role = "Пользователь" if message.role == "user" else "Бот"
        lines.append(f"• <b>{role}</b>: {html_escape(message.content[:250])}")
    return "\n".join(lines)


def format_status_card(stage: str, urgency: str, perspective: str, context: dict) -> str:
    lines = [
        "<b>Текущий статус</b>",
        f"Этап: {html_escape(stage)}",
        f"Срочность: {html_escape(urgency)}",
        f"Перспективность: {html_escape(perspective)}",
        "",
        f"Имя: {html_escape(str(context.get('name') or 'не указано'))}",
        f"Телефон: {html_escape(str(context.get('phone') or 'не указан'))}",
        f"Telegram: {html_escape(str(context.get('telegram') or 'не указан'))}",
        f"Регион: {html_escape(str(context.get('region') or 'не указан'))}",
        f"Дата ДТП: {html_escape(str(context.get('accident_date') or 'не указана'))}",
        f"Документы: {html_escape(str(context.get('documents') or 'не указаны'))}",
        f"Повреждения: {html_escape(str(context.get('damage') or 'не указаны'))}",
    ]
    return "\n".join(lines)


def format_company_contacts(
    company_name: str,
    phone: str | None,
    telegram: str | None,
    website: str | None,
    address: str | None,
) -> str:
    lines = [f"<b>{html_escape(company_name)}</b>", "", "Связаться с нами:"]
    if phone:
        lines.append(f"📞 Телефон: {html_escape(phone)}")
    if telegram:
        value = telegram if telegram.startswith("@") else f"@{telegram}"
        lines.append(f"✈️ Telegram: {html_escape(value)}")
    if website:
        lines.append(f"🌐 Сайт: {html_escape(website)}")
    if address:
        lines.append(f"📍 Адрес: {html_escape(address)}")

    if len(lines) == 3:
        lines.extend(["", "Контакты пока не настроены в конфигурации бота."])
    return "\n".join(lines)


def format_consult_reply(
    reply: str,
    next_question: str = "",
    needs_operator: bool = False,
    ask_contacts: bool = False,
) -> str:
    parts = [reply.strip()]
    if next_question:
        parts.append(next_question.strip())
    if ask_contacts:
        parts.append("Если удобно, оставьте имя и телефон — передам обращение специалисту.")
    if needs_operator:
        parts.append("Могу передать обращение специалисту.")
    return "\n\n".join(part for part in parts if part)


def format_command_help() -> str:
    return (
        "<b>Команды</b>\n"
        "/start — начать диалог\n"
        "/consult — консультация\n"
        "/contacts — контакты компании\n"
        "/status — статус обращения\n"
        "/history — история диалога\n"
        "/operator — связаться со специалистом\n"
        "/cancel — отменить текущий сценарий\n"
        "/help — помощь"
    )
