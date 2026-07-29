from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def consult_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👤 Оператор", callback_data="consult:operator"),
                InlineKeyboardButton(text="📞 Контакты", callback_data="consult:contacts"),
            ],
            [
                InlineKeyboardButton(text="❌ Отменить", callback_data="consult:cancel"),
            ],
        ]
    )
