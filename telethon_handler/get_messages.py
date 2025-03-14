import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from deepseek.deepsekk import analyze_with_deepseek
from news import set_news_text
from aiogram import Bot
from config import config

# Инициализация бота
bot = Bot(token=config.tg_bot_token)

channel_ids = [-1001203560567, -1002208140065, -1001268341728, -1001337895647, -1001000499465]

last_message_ids = {channel_id: None for channel_id in channel_ids}


async def get_channel_messages(client, channel_id, limit=5):
    messages = []
    async for message in client.iter_messages(channel_id, limit=limit):
        if message.text:  # Фильтруем только текстовые сообщения
            messages.append(message.text)
    return messages


async def telethon_channels_main():
    """Основная асинхронная функция"""
    async with TelegramClient(StringSession(config.telethon_session), config.telethon_id, config.telethon_hash) as client:

        @client.on(events.NewMessage(chats=channel_ids))
        async def new_message_handler(event):
            channel_id = event.chat_id
            message_id = event.message.id

            if last_message_ids[channel_id] is None or message_id > last_message_ids[channel_id]:
                last_message_ids[channel_id] = message_id  # Обновляем ID последнего сообщения

                latest_messages = await get_channel_messages(client, channel_id, limit=5)

                if latest_messages:
                    analysis_result = analyze_with_deepseek(latest_messages)
                    set_news_text(analysis_result)

                    await bot.send_message(
                        chat_id=-1002467387559,
                        text=f"{analysis_result}",
                        parse_mode="HTML"
                    )

        print("✅ Бот запущен и отслеживает каналы...")
        await client.run_until_disconnected()  # Ожидание новых сообщений
