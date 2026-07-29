from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.consultation import consult_keyboard
from bot.states.consultation import Consultation, ContactForm
from config.settings import Settings
from services.ai_service import AIService, AIServiceError, AISummaryResult
from services.conversation_service import ConversationService, ConversationSnapshot
from services.formatter import format_command_help, format_consult_reply, format_recent_history, format_status_card
from services.lead_service import LeadService
from services.prompt_service import PromptService
from storage.models import UserRecord
from storage.repository import Repository
from utils.helpers import split_text

logger = logging.getLogger(__name__)
router = Router()


async def ensure_user(repo: Repository, message: Message) -> None:
    user = message.from_user
    if user is None:
        return
    await repo.ensure_user(
        UserRecord(
            chat_id=message.chat.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
        )
    )


async def get_snapshot(repo: Repository, conversation_service: ConversationService, chat_id: int) -> ConversationSnapshot:
    conv = await repo.get_conversation(chat_id)
    return conversation_service.build_snapshot(
        chat_id=chat_id,
        context=conv.context,
        operator_requested=conv.operator_requested,
        handed_off=conv.handed_off,
    )


async def notify_admins(
    bot,
    settings: Settings,
    lead_service: LeadService,
    snapshot: ConversationSnapshot,
    ai_result: AISummaryResult | None = None,
    operator_note: str | None = None,
) -> None:
    lead = await lead_service.upsert_lead_from_snapshot(
        chat_id=snapshot.chat_id,
        snapshot=snapshot,
        ai_result=ai_result,
        operator_note=operator_note,
        status="handoff" if snapshot.handed_off else "new",
    )
    await lead_service.notify_admins(bot, lead)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, repo: Repository) -> None:
    await ensure_user(repo, message)
    await state.set_state(Consultation.active)
    await repo.save_message(message.chat.id, "user", message.text or "/start")
    conv = await repo.get_conversation(message.chat.id)
    conv.state = "consultation"
    conv.stage = "intake"
    conv.context.setdefault("source", "telegram")
    await repo.update_conversation(conv)
    await message.answer(
        "Здравствуйте. Я помогу первично разобрать ситуацию по ДТП или страховому спору.\n"
        "Напишите, что произошло, и я задам несколько уточняющих вопросов.",
        reply_markup=consult_keyboard(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message, repo: Repository) -> None:
    await repo.save_message(message.chat.id, "user", message.text or "/help")
    await message.answer(format_command_help())


@router.message(Command("consult"))
async def cmd_consult(message: Message, state: FSMContext, repo: Repository) -> None:
    await ensure_user(repo, message)
    await state.set_state(Consultation.active)
    await repo.save_message(message.chat.id, "user", message.text or "/consult")
    await message.answer("Хорошо, давайте разберём ситуацию. Кратко опишите, что случилось.", reply_markup=consult_keyboard())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, repo: Repository) -> None:
    await repo.save_message(message.chat.id, "user", message.text or "/cancel")
    await state.clear()
    conv = await repo.get_conversation(message.chat.id)
    conv.state = None
    await repo.update_conversation(conv)
    await message.answer("Текущий сценарий отменён. Можем начать заново в любой момент.")


@router.message(Command("status"))
async def cmd_status(message: Message, repo: Repository, conversation_service: ConversationService) -> None:
    await repo.save_message(message.chat.id, "user", message.text or "/status")
    snapshot = await get_snapshot(repo, conversation_service, message.chat.id)
    await message.answer(format_status_card(snapshot.stage, snapshot.urgency, snapshot.perspective, snapshot.context))


@router.message(Command("history"))
async def cmd_history(message: Message, repo: Repository) -> None:
    await repo.save_message(message.chat.id, "user", message.text or "/history")
    history = await repo.list_messages(message.chat.id, limit=10)
    await message.answer(format_recent_history(history))


@router.message(Command("contacts"))
async def cmd_contacts(message: Message, state: FSMContext, repo: Repository) -> None:
    await repo.save_message(message.chat.id, "user", message.text or "/contacts")
    await state.set_state(ContactForm.name)
    await message.answer("Давайте запишем контакты. Как вас зовут?")


@router.message(Command("operator"))
async def cmd_operator(
    message: Message,
    repo: Repository,
    conversation_service: ConversationService,
    lead_service: LeadService,
    settings: Settings,
) -> None:
    await repo.save_message(message.chat.id, "user", message.text or "/operator")
    await repo.set_handoff(message.chat.id, True, True)
    snapshot = await get_snapshot(repo, conversation_service, message.chat.id)
    await notify_admins(message.bot, settings, lead_service, snapshot, operator_note="Пользователь запросил оператора")
    await message.answer(
        "Хорошо, я передам обращение специалисту. Чтобы ускорить связь, можно сразу отправить имя и телефон.",
        reply_markup=consult_keyboard(),
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message, settings: Settings, lead_service: LeadService) -> None:
    if settings.admin_chat_id and message.chat.id != settings.admin_chat_id:
        return
    leads = await lead_service.repository.list_recent_leads(limit=5)
    if not leads:
        await message.answer("Пока новых лидов нет.")
        return
    text = ["<b>Последние лиды</b>"]
    for lead in leads:
        text.append(f"• ID {lead.chat_id} | {lead.name or 'без имени'} | {lead.phone or 'без телефона'} | {lead.status} | {lead.stage or '-'}")
    await message.answer("\n".join(text))


@router.callback_query(F.data == "consult:cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext, repo: Repository) -> None:
    await state.clear()
    chat_id = callback.message.chat.id if callback.message else callback.from_user.id
    conv = await repo.get_conversation(chat_id)
    conv.state = None
    await repo.update_conversation(conv)
    await callback.answer("Отменено")
    if callback.message:
        await callback.message.answer("Текущий сценарий отменён.")


@router.callback_query(F.data == "consult:contacts")
async def cb_contacts(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ContactForm.name)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Давайте запишем контакты. Как вас зовут?")


@router.callback_query(F.data == "consult:operator")
async def cb_operator(
    callback: CallbackQuery,
    repo: Repository,
    conversation_service: ConversationService,
    lead_service: LeadService,
    settings: Settings,
) -> None:
    chat_id = callback.message.chat.id if callback.message else callback.from_user.id
    await repo.set_handoff(chat_id, True, True)
    snapshot = await get_snapshot(repo, conversation_service, chat_id)
    await notify_admins(callback.bot, settings, lead_service, snapshot, operator_note="Пользователь нажал кнопку оператора")
    await callback.answer("Передаю специалисту")
    if callback.message:
        await callback.message.answer("Хорошо, передаю диалог специалисту. Можете оставить контакты, чтобы вам быстрее написали.")


@router.message(ContactForm.name)
async def contact_name(message: Message, state: FSMContext, repo: Repository) -> None:
    await ensure_user(repo, message)
    name = (message.text or "").strip()
    await state.update_data(name=name)
    await repo.merge_context(message.chat.id, {"name": name})
    await repo.save_message(message.chat.id, "user", message.text or "")
    await state.set_state(ContactForm.phone)
    await message.answer("Спасибо. Теперь отправьте номер телефона.")


@router.message(ContactForm.phone)
async def contact_phone(message: Message, state: FSMContext, repo: Repository) -> None:
    phone = (message.text or "").strip()
    await repo.save_message(message.chat.id, "user", message.text or "")
    await state.update_data(phone=phone)
    await repo.merge_context(message.chat.id, {"phone": phone})
    await state.set_state(ContactForm.telegram)
    await message.answer("Отлично. Укажите Telegram, если удобно, или напишите 'нет'.")


@router.message(ContactForm.telegram)
async def contact_telegram(message: Message, state: FSMContext, repo: Repository) -> None:
    raw = (message.text or "").strip()
    await repo.save_message(message.chat.id, "user", message.text or "")
    tg = None if raw.lower() == "нет" else raw
    if tg and not tg.startswith("@"):
        tg = "@" + tg
    await state.update_data(telegram=tg)
    await repo.merge_context(message.chat.id, {"telegram": tg})
    await state.set_state(ContactForm.time)
    await message.answer("И последнее: когда вам удобнее, чтобы с вами связались?")


@router.message(ContactForm.time)
async def contact_time(
    message: Message,
    state: FSMContext,
    repo: Repository,
    conversation_service: ConversationService,
    lead_service: LeadService,
    settings: Settings,
) -> None:
    preferred_time = (message.text or "").strip()
    await repo.save_message(message.chat.id, "user", message.text or "")
    await repo.merge_context(message.chat.id, {"preferred_time": preferred_time})
    conv = await repo.get_conversation(message.chat.id)
    conv.handed_off = True
    conv.operator_requested = True
    conv.state = "handoff"
    await repo.update_conversation(conv)
    snapshot = await get_snapshot(repo, conversation_service, message.chat.id)
    lead = await lead_service.upsert_lead_from_snapshot(
        chat_id=message.chat.id,
        snapshot=snapshot,
        ai_result=None,
        operator_note=f"Удобное время связи: {preferred_time}",
        status="handoff",
    )
    await lead_service.notify_admins(message.bot, lead)
    await state.clear()
    await message.answer("Спасибо. Я зафиксировал контакты и передал всё специалисту.", reply_markup=consult_keyboard())


async def process_consultation_message(
    message: Message,
    state: FSMContext,
    repo: Repository,
    conversation_service: ConversationService,
    prompt_service: PromptService,
    ai_service: AIService,
    lead_service: LeadService,
    settings: Settings,
) -> None:
    await ensure_user(repo, message)
    text = (message.text or message.caption or "").strip()
    if not text or text.startswith("/"):
        return

    await repo.save_message(message.chat.id, "user", text)
    conv = await repo.get_conversation(message.chat.id)
    if conv.handed_off:
        await message.answer("Диалог уже передан специалисту. Я не буду мешать, но могу помочь собрать контакты, если нужно.")
        return

    extracted = conversation_service.extract_fields(text, conv.context)
    conv.context.update(extracted)
    conv.state = "consultation"
    await repo.update_conversation(conv)

    snapshot = conversation_service.build_snapshot(
        chat_id=message.chat.id,
        context=conv.context,
        operator_requested=conv.operator_requested,
        handed_off=conv.handed_off,
    )
    recent = await repo.list_messages(message.chat.id, limit=settings.max_history_messages)
    recent_payload = [{"role": item.role, "content": item.content} for item in recent]

    messages = prompt_service.build_consultation_messages(
        snapshot=snapshot,
        recent_messages=recent_payload,
        user_message=text,
        tone=settings.default_tone,
        language=settings.default_language,
    )

    try:
        ai_result = await ai_service.chat_consultation(messages)
    except AIServiceError:
        final_reply = f"Понял вас. {snapshot.current_question}"
        await message.answer(final_reply, reply_markup=consult_keyboard())
        return

    final_reply = format_consult_reply(
        reply=ai_result.reply or "Понял. Давайте уточним несколько деталей.",
        next_question=ai_result.next_question or snapshot.current_question,
        needs_operator=ai_result.needs_operator,
        ask_contacts=ai_result.ask_contacts,
    )

    conv = await repo.get_conversation(message.chat.id)
    conv.context.update(extracted)
    conv.stage = ai_result.stage or snapshot.stage
    conv.last_ai_reply = final_reply
    await repo.update_conversation(conv)

    ai_summary = AISummaryResult(
        summary=ai_result.summary,
        recommended_next_step=ai_result.next_question or snapshot.current_question,
        priority=ai_result.urgency,
        comment=ai_result.ai_comment,
        raw_text=ai_result.raw_text,
    )

    lead = await lead_service.upsert_lead_from_snapshot(
        chat_id=message.chat.id,
        snapshot=conversation_service.build_snapshot(
            chat_id=message.chat.id,
            context=conv.context,
            operator_requested=ai_result.needs_operator or conv.operator_requested,
            handed_off=conv.handed_off,
        ),
        ai_result=ai_summary,
        status="handoff" if (ai_result.needs_operator or snapshot.stage == "ready_for_handoff") else "new",
    )

    if ai_result.needs_operator or snapshot.stage == "ready_for_handoff":
        conv.handed_off = True
        conv.operator_requested = True
        await repo.update_conversation(conv)
        await lead_service.notify_admins(message.bot, lead)

    chunks = split_text(final_reply)
    for index, chunk in enumerate(chunks):
        await message.answer(chunk, reply_markup=consult_keyboard() if index == 0 else None)

    if ai_result.ask_contacts and not (conv.context.get("phone") or conv.context.get("telegram")):
        await message.answer("Чтобы специалист связался быстрее, можно оставить имя и телефон.", reply_markup=consult_keyboard())


@router.message(F.text)
async def fallback_text(
    message: Message,
    state: FSMContext,
    repo: Repository,
    conversation_service: ConversationService,
    prompt_service: PromptService,
    ai_service: AIService,
    lead_service: LeadService,
    settings: Settings,
) -> None:
    if (message.text or "").startswith("/"):
        return
    current_state = await state.get_state()
    if current_state is None:
        await state.set_state(Consultation.active)
    await process_consultation_message(
        message=message,
        state=state,
        repo=repo,
        conversation_service=conversation_service,
        prompt_service=prompt_service,
        ai_service=ai_service,
        lead_service=lead_service,
        settings=settings,
    )
