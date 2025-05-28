import logging

from telethon import TelegramClient, events, functions, types
from telethon.sessions import StringSession
from deepseek.deepsekk import analyze_with_deepseek
from news import set_file_text
from aiogram import Bot
from config import config
from aiogram.enums import ParseMode
import os
import asyncio
import time
import base64
import json
from datetime import datetime
from telethon.tl.types import Message
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
from aiogram.client.default import DefaultBotProperties


bot = Bot(token=config.tg_bot_token, default=DefaultBotProperties(parse_mode="HTML"))

channel_ids = [-1001203560567, -1002208140065, -1001268341728, -1001337895647, -1001000499465]

last_message_ids = {channel_id: None for channel_id in channel_ids}


import re


async def get_channel_messages(client, channel_id, limit=5):
    messages = []
    async for message in client.iter_messages(channel_id, limit=limit):
        if message.text:  
            messages.append(message.text)
    return messages


def escape_markdown_v2(text):
    special_chars = r'_*[]()~`>#+-=|{}.!'
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

async def telethon_channels_main():
    """Основная асинхронная функция"""
    async with TelegramClient(StringSession(config.telethon_session), config.telethon_id,
                              config.telethon_hash) as client:
        @client.on(events.NewMessage(chats=channel_ids))
        async def new_message_handler(event):
            message_text = event.message.text

            if message_text:
                analysis_result = await analyze_with_deepseek([message_text])
                logging.info("ChatGPT: " + analysis_result)
                if analysis_result != "null":
                    await bot.send_message(
                        chat_id=-1002467387559,
                        text=analysis_result.replace("**", "*"),
                        parse_mode=ParseMode.MARKDOWN
                    )
                    set_file_text('old_news', message_text)

        print("Бот запущен")
        await client.run_until_disconnected()