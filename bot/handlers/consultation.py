from __future__ import annotations

import base64
import logging
from io import BytesIO

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.consultation import consult_keyboard
from bot.states.consultation import Consultation, ContactForm
from config.settings import Settings
from services.ai_service import AIService, AIServiceError, AISummaryResult
from services.conversation_service import ConversationService, ConversationSnapshot
from services.formatter import (
    format_company_contacts,
    format_command_help,
    format_consult_reply,
    format_recent_history,
    format_status_card,
)
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


async def get_snapshot(
    repo: Repository,
    conversation_service: ConversationService,
    chat_id: int,
) -> ConversationSnapshot:
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


async def start_contact_form(message: Message, state: FSMContext) -> None:
    await state.set_state(ContactForm.name)
    await message.answer("Как к вам обращаться?")


async def handoff_after_contacts(
    message: Message,
    state: FSMContext,
    repo: Repository,
    conversation_service: ConversationService,
    lead_service: LeadService,
) -> None:
    conv = await repo.get_conversation(message.chat.id)
    conv.handed_off = True
    conv.operator_requested = True
    conv.state = "handoff"
    conv.stage = "handoff"
    await repo.update_conversation(conv)

    snapshot = await get_snapshot(repo, conversation_service, message.chat.id)
    lead = await lead_service.upsert_lead_from_snapshot(
        chat_id=message.chat.id,
        snapshot=snapshot,
        ai_result=None,
        operator_note="Пользователь запросил связь со специалистом",
        status="handoff",
    )
    await lead_service.notify_admins(message.bot, lead)

    await state.clear()
    await message.answer(
        "Готово. Контакты сохранил и передал обращение специалисту.",
        reply_markup=consult_keyboard(),
    )


def _has_contact(context: dict) -> bool:
    return bool(context.get("phone") or context.get("telegram"))


def _build_image_url(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


async def _get_photo_for_ai(message: Message) -> tuple[str, bytes] | None:
    if not message.photo:
        return None

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    buffer = BytesIO()
    await message.bot.download(file, destination=buffer)
    return "image/jpeg", buffer.getvalue()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, repo: Repository) -> None:
    await ensure_user(repo, message)
    await state.set_state(Consultation.active)
    await repo.save_message(message.chat.id, "user", message.text or "/start")

    conv = await repo.get_conversation(message.chat.id)
    conv.state = "consultation"
    conv.stage = "intake"
    conv.handed_off = False
    conv.operator_requested = False
    conv.context.setdefault("source", "telegram")
    await repo.update_conversation(conv)

    await message.answer(
        "Здравствуйте. Опишите, что произошло — можно обычными словами, как есть. "
        "Я помогу разобраться и подскажу, что делать дальше.",
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
    await message.answer(
        "Опишите ситуацию своими словами. Что случилось?",
        reply_markup=consult_keyboard(),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, repo: Repository) -> None:
    await repo.save_message(message.chat.id, "user", message.text or "/cancel")
    await state.clear()
    conv = await repo.get_conversation(message.chat.id)
    conv.state = None
    conv.handed_off = False
    conv.operator_requested = False
    await repo.update_conversation(conv)
    await message.answer("Хорошо, текущий диалог сбросил.")


@router.message(Command("status"))
async def cmd_status(
    message: Message,
    repo: Repository,
    conversation_service: ConversationService,
) -> None:
    await repo.save_message(message.chat.id, "user", message.text or "/status")
    snapshot = await get_snapshot(repo, conversation_service, message.chat.id)
    await message.answer(
        format_status_card(
            snapshot.stage,
            snapshot.urgency,
            snapshot.perspective,
            snapshot.context,
        )
    )


@router.message(Command("history"))
async def cmd_history(message: Message, repo: Repository) -> None:
    await repo.save_message(message.chat.id, "user", message.text or "/history")
    history = await repo.list_messages(message.chat.id, limit=10)
    await message.answer(format_recent_history(history))


@router.message(Command("contacts"))
async def cmd_contacts(message: Message, settings: Settings, repo: Repository) -> None:
    await repo.save_message(message.chat.id, "user", message.text or "/contacts")
    await message.answer(
        format_company_contacts(
            company_name=settings.company_name,
            phone=settings.contact_phone,
            telegram=settings.contact_telegram,
            website=settings.contact_website,
            address=settings.contact_address,
        ),
        reply_markup=consult_keyboard(),
    )


@router.message(Command("operator"))
async def cmd_operator(
    message: Message,
    state: FSMContext,
    repo: Repository,
) -> None:
    await repo.save_message(message.chat.id, "user", message.text or "/operator")
    await start_contact_form(message, state)


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
        text.append(
            f"• ID {lead.chat_id} | {lead.name or 'без имени'} | "
            f"{lead.phone or 'без телефона'} | {lead.status} | {lead.stage or '-'}"
        )
    await message.answer("\n".join(text))


@router.callback_query(F.data == "consult:cancel")
async def cb_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    repo: Repository,
) -> None:
    await state.clear()
    chat_id = callback.message.chat.id if callback.message else callback.from_user.id
    conv = await repo.get_conversation(chat_id)
    conv.state = None
    conv.handed_off = False
    conv.operator_requested = False
    await repo.update_conversation(conv)
    await callback.answer("Сбросил")

    if callback.message:
        await callback.message.answer("Хорошо, начнём заново.")


@router.callback_query(F.data == "consult:contacts")
async def cb_contacts(
    callback: CallbackQuery,
    settings: Settings,
) -> None:
    await callback.answer()

    if callback.message:
        await callback.message.answer(
            format_company_contacts(
                company_name=settings.company_name,
                phone=settings.contact_phone,
                telegram=settings.contact_telegram,
                website=settings.contact_website,
                address=settings.contact_address,
            ),
            reply_markup=consult_keyboard(),
        )


@router.callback_query(F.data == "consult:operator")
async def cb_operator(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    if callback.message:
        await start_contact_form(callback.message, state)


@router.message(ContactForm.name)
async def contact_name(message: Message, state: FSMContext, repo: Repository) -> None:
    await ensure_user(repo, message)
    name = (message.text or "").strip()

    if not name:
        await message.answer("Напишите, пожалуйста, имя.")
        return

    await state.update_data(name=name)
    await repo.merge_context(message.chat.id, {"name": name})
    await repo.save_message(message.chat.id, "user", name)
    await state.set_state(ContactForm.phone)
    await message.answer("Оставьте номер телефона, чтобы специалист мог связаться с вами.")


@router.message(ContactForm.phone)
async def contact_phone(
    message: Message,
    state: FSMContext,
    repo: Repository,
    conversation_service: ConversationService,
    lead_service: LeadService,
) -> None:
    phone = (message.text or "").strip()

    if not phone:
        await message.answer("Нужен номер телефона. Можно просто отправить его сообщением.")
        return

    await repo.save_message(message.chat.id, "user", phone)
    await repo.merge_context(message.chat.id, {"phone": phone})
    await handoff_after_contacts(
        message,
        state,
        repo,
        conversation_service,
        lead_service,
    )


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
    photo = await _get_photo_for_ai(message) if message.photo else None

    if not text and not photo:
        return

    display_text = text or "Пользователь отправил фотографию без подписи."
    if photo:
        display_text = f"{display_text}\n[Фото прикреплено]"

    await repo.save_message(message.chat.id, "user", display_text)

    conv = await repo.get_conversation(message.chat.id)
    if conv.handed_off:
        await message.answer(
            "Обращение уже передано специалисту. Новые детали сохраню в диалоге.",
            reply_markup=consult_keyboard(),
        )
        return

    extracted = conversation_service.extract_fields(text, conv.context) if text else {
        "source": conv.context.get("source") or "telegram"
    }
    conv.context.update(extracted)
    conv.state = "consultation"
    await repo.update_conversation(conv)

    snapshot = conversation_service.build_snapshot(
        chat_id=message.chat.id,
        context=conv.context,
        operator_requested=conv.operator_requested,
        handed_off=conv.handed_off,
    )

    recent = await repo.list_messages(
        message.chat.id,
        limit=settings.max_history_messages,
    )
    recent_payload = [
        {"role": item.role, "content": item.content}
        for item in recent
    ]

    messages = prompt_service.build_consultation_messages(
        snapshot=snapshot,
        recent_messages=recent_payload,
        user_message=text or "На фотографии находится материал по обращению пользователя.",
        tone=settings.default_tone,
        language=settings.default_language,
        image_attached=photo is not None,
    )

    if photo:
        mime_type, image_bytes = photo
        user_content = messages[-1]["content"]
        messages[-1]["content"] = [
            {"type": "text", "text": user_content},
            {
                "type": "image_url",
                "image_url": {"url": _build_image_url(image_bytes, mime_type)},
            },
        ]

    try:
        ai_result = await ai_service.chat_consultation(messages)
    except AIServiceError:
        fallback_question = snapshot.current_question
        fallback = "Вижу обращение. "
        if photo:
            fallback += "Фото получил. "
        if fallback_question:
            fallback += fallback_question
        await message.answer(fallback, reply_markup=consult_keyboard())
        return

    final_reply = format_consult_reply(
        reply=ai_result.reply or "Расскажите чуть подробнее, что произошло.",
        next_question=ai_result.next_question,
        needs_operator=False,
        ask_contacts=False,
    )

    conv = await repo.get_conversation(message.chat.id)
    conv.context.update(extracted)
    conv.stage = ai_result.stage or snapshot.stage
    conv.last_ai_reply = final_reply
    await repo.update_conversation(conv)

    ai_summary = AISummaryResult(
        summary=ai_result.summary,
        recommended_next_step=ai_result.next_question,
        priority=ai_result.urgency,
        comment=ai_result.ai_comment,
        raw_text=ai_result.raw_text,
    )

    should_handoff = ai_result.needs_operator or ai_result.stage == "ready_for_handoff"

    current_snapshot = conversation_service.build_snapshot(
        chat_id=message.chat.id,
        context=conv.context,
        operator_requested=conv.operator_requested or should_handoff,
        handed_off=conv.handed_off,
    )

    lead = await lead_service.upsert_lead_from_snapshot(
        chat_id=message.chat.id,
        snapshot=current_snapshot,
        ai_result=ai_summary,
        status="new",
    )

    for index, chunk in enumerate(split_text(final_reply)):
        await message.answer(
            chunk,
            reply_markup=consult_keyboard() if index == 0 else None,
        )

    if should_handoff:
        if _has_contact(conv.context):
            conv.handed_off = True
            conv.operator_requested = True
            conv.state = "handoff"
            conv.stage = "handoff"
            await repo.update_conversation(conv)
            await lead_service.notify_admins(message.bot, lead)
            await message.answer(
                "Картина понятна. Передал обращение специалисту.",
                reply_markup=consult_keyboard(),
            )
            return

        await message.answer(
            "Картина уже понятна. Оставьте имя и телефон — передам всё специалисту.",
            reply_markup=consult_keyboard(),
        )
        await state.set_state(ContactForm.name)
        return

    if ai_result.ask_contacts and not _has_contact(conv.context):
        await message.answer(
            "Для связи со специалистом можно оставить имя и телефон.",
            reply_markup=consult_keyboard(),
        )


@router.message(F.photo)
async def photo_handler(
    message: Message,
    state: FSMContext,
    repo: Repository,
    conversation_service: ConversationService,
    prompt_service: PromptService,
    ai_service: AIService,
    lead_service: LeadService,
    settings: Settings,
) -> None:
    current_state = await state.get_state()
    if current_state in {
        ContactForm.name.state,
        ContactForm.phone.state,
    }:
        await message.answer("Для контакта лучше отправить имя или номер обычным сообщением.")
        return

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
    if current_state in {
        ContactForm.name.state,
        ContactForm.phone.state,
    }:
        return

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
