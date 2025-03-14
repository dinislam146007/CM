import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.bot import DefaultBotProperties
from config import config
from basic.handlers import router
from db import create_tables
from telethon_handler.get_messages import telethon_channels_main

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.tg_bot_token, session=AiohttpSession(), default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)

async def on_startup():
    logging.info("Бот запущен")

async def on_shutdown():
    await dp.storage.close()
    await bot.close()
    logging.info("Бот остановлен")

dp.startup.register(on_startup)
dp.shutdown.register(on_shutdown)

async def main():
    await create_tables()
    await dp.start_polling(bot)
    await telethon_channels_main()

if __name__ == "__main__":
    asyncio.run(main())
