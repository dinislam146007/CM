from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from config import config


async def main():
    async with TelegramClient(StringSession(config.telethon_session), config.telethon_id, config.telethon_hash) as client:
        await client.send_message(6634277726, 'Тестовое сообщение')

import asyncio
asyncio.run(main())
