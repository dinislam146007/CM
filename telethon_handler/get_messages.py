import logging

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from deepseek.deepsekk import analyze_with_deepseek
from news import set_file_text
from aiogram import Bot
from config import config
from aiogram.enums import ParseMode



# Инициализация бота
bot = Bot(token=config.tg_bot_token)

channel_ids = [-1001203560567, -1002208140065, -1001268341728, -1001337895647, -1001000499465]

last_message_ids = {channel_id: None for channel_id in channel_ids}

def escape_markdown_v2(text):
    """Экранирует специальные символы для MarkdownV2 в aiogram 3.x"""
    special_chars = r'_*[]()~`>#+-=|{}.!$'
    return ''.join(f'\\{char}' if char in special_chars else char for char in text)


async def get_channel_messages(client, channel_id, limit=5):
    messages = []
    async for message in client.iter_messages(channel_id, limit=limit):
        if message.text:  # Фильтруем только текстовые сообщения
            messages.append(message.text)
    return messages




async def telethon_channels_main():
    """Основная асинхронная функция"""
    async with TelegramClient(StringSession(config.telethon_session), config.telethon_id,
                              config.telethon_hash) as client:
        @client.on(events.NewMessage(chats=channel_ids))
        async def new_message_handler(event):
            message_text = event.message.text  # Получаем текст нового сообщения


            if message_text:  # Проверяем, что сообщение не пустое
                analysis_result = await analyze_with_deepseek([message_text])  # Анализируем только одно сообщение
                if analysis_result != "None":
                    logging.info("ChatGPT: " + analysis_result)
                    await bot.send_message(
                        chat_id=-1002467387559,
                        text=escape_markdown_v2(analysis_result),
                        parse_mode=ParseMode.MARKDOWN_V2  # Указали разметку
                    )
                    set_file_text('news',analysis_result)
                    set_file_text('old_news', message_text)


        print("✅ Бот запущен и отслеживает каналы...")
        await client.run_until_disconnected()  # Ожидание новых сообщений