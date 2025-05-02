import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.bot import DefaultBotProperties
from config import config
from basic.handlers import router
from db import create_tables
from db.update_schema import update_schema
from telethon_handler.get_messages import telethon_channels_main
from strategy_logic.admin_commands import register_trading_settings_handlers

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.tg_bot_token, session=AiohttpSession(), default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)

# Register trading settings handlers
register_trading_settings_handlers(dp)

async def on_startup():
    logging.info("Бот запущен")

async def on_shutdown():
    await dp.storage.close()
    await bot.close()
    logging.info("Бот остановлен")

dp.startup.register(on_startup)
dp.shutdown.register(on_shutdown)

async def main():
    # Создаем задачи для Telethon и Aiogram
    telethon_task = asyncio.create_task(telethon_channels_main())
    
    # Create database tables and update schema
    await create_tables()
    await update_schema()  # Update schema for futures trading

    try:
        await dp.start_polling(bot)  # Основной процесс бота
    finally:
        telethon_task.cancel()  # Останавливаем Telethon при завершении бота
        await telethon_task

if __name__ == "__main__":
    asyncio.run(main())
