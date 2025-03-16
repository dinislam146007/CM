from telethon import TelegramClient, events
from telethon.sessions import StringSession
from deepseek.deepsekk import analyze_with_deepseek
from news import set_file_text
from aiogram import Bot
from config import config
from aiogram.enums import ParseMode
import re


# Инициализация бота
bot = Bot(token=config.tg_bot_token)

channel_ids = [-1001203560567, -1002208140065, -1001268341728, -1001337895647, -1001000499465]

last_message_ids = {channel_id: None for channel_id in channel_ids}

def escape_telegram_markdown_v2(text: str) -> str:
    """
    Экранирует специальные символы для корректного отображения в Telegram MarkdownV2.
    """
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)


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
            channel_id = event.chat_id
            message_text = event.message.text  # Получаем текст нового сообщения


            if message_text:  # Проверяем, что сообщение не пустое
                analysis_result = await analyze_with_deepseek([message_text])  # Анализируем только одно сообщение
                if analysis_result != "None":
                    await bot.send_message(
                        chat_id=-1002467387559,
                        text=f"{analysis_result}",
                        parse_mode="HTML"  # Указали разметку
                    )
                    set_file_text('news',analysis_result)
                    set_file_text('old_news', message_text)


        print("✅ Бот запущен и отслеживает каналы...")
        await client.run_until_disconnected()  # Ожидание новых сообщений