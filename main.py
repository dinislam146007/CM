import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.bot import DefaultBotProperties
from config import config
from basic.handlers import router
from db.create_table import create_tables
from db.update_schema import update_schema
from telethon_handler.get_messages import telethon_channels_main
from strategy_logic.admin_commands import trading_router
from strategy_logic.cm_notification_processor import start_notification_processor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from strategy_logic.get_all_coins import get_usdt_pairs

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.tg_bot_token, session=AiohttpSession(), default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)
dp.include_router(trading_router)

async def on_startup():
    logging.info("Бот запущен")
    # Start CM notification processor
    start_notification_processor()
    logging.info("CM notification processor started")

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
