from aiogram import Router

from bot.handlers.consultation import router as consultation_router

router = Router()
router.include_router(consultation_router)
