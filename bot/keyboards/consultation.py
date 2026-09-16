from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def consult_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📞 Мои контакты", callback_data="consult:contacts"),
                InlineKeyboardButton(text="👤 Связаться со специалистом", callback_data="consult:operator"),
            ],
            [
                InlineKeyboardButton(text="↩️ Начать заново", callback_data="consult:cancel"),
            ],
        ]
    )
