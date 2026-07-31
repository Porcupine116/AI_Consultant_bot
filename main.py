from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import router as main_router
from config.settings import get_settings
from services.ai_service import AIService
from services.conversation_service import ConversationService
from services.lead_service import LeadService
from services.prompt_service import PromptService
from storage.db import Database
from storage.repository import Repository
from utils.logger import setup_logging


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    logging.getLogger(__name__).info("Starting bot")

    db = Database(settings.database_path)
    await db.init()

    repository = Repository(db)
    prompt_service = PromptService()
    conversation_service = ConversationService()
    lead_service = LeadService(repository, settings)
    ai_service = AIService(settings)

    session = AiohttpSession(proxy="http://user385924:x0wdeh@84.32.156.9:3166")
    bot = Bot(token=settings.bot_token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(main_router)

    try:
        await dp.start_polling(
            bot,
            repository=repository,
            prompt_service=prompt_service,
            conversation_service=conversation_service,
            lead_service=lead_service,
            ai_service=ai_service,
            settings=settings,
        )
    finally:
        await ai_service.aclose()
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
