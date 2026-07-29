from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Consultation(StatesGroup):
    active = State()


class ContactForm(StatesGroup):
    name = State()
    phone = State()
    telegram = State()
    time = State()
