from telethon_handler.create_client import client
from telethon import events
from deepseek.deepsekk import analyze_with_deepseek
from news import *
from aiogram import Bot
from config import config

bot = Bot(token=config.tg_bot_token)

# Список каналов, которые ты хочешь отслеживать
channel_ids = [-1001203560567, -1002208140065]

# Словарь для хранения последнего ID сообщения для каждого канала
last_message_ids = {channel_id: None for channel_id in channel_ids}


async def get_channel_messages(client, channel_id, limit=5):
    """Получает последние 'limit' сообщений из указанного канала."""
    messages = []
    async for message in client.iter_messages(channel_id, limit=limit):
        messages.append(message.text)
    return messages

# Обработчик новых сообщений
@client.on(events.NewMessage(chats=channel_ids))
async def new_message_handler(event):
    channel_id = event.chat_id
    message_id = event.message.id

    if last_message_ids[channel_id] is None or message_id > last_message_ids[channel_id]:
        last_message_ids[channel_id] = message_id  # Обновляем ID последнего сообщения

        latest_messages = await get_channel_messages(client, channel_id, limit=5)

        if latest_messages:
            analysis_result = await analyze_with_deepseek(latest_messages)
            set_news_text(analysis_result)
            await bot.send_message(chat_id=-1002467387559, text=f"{analysis_result}")
            #print(f"🔍 Deepseek Analysis for channel {channel_id}:\n{analysis_result}")


# Запускаем клиента
#client.start()

"""async def main():
    await client.start()  # Запуск клиента с восстановлением сессии
    messages = await get_channel_messages(channel_id)

    # Выводим сообщения
    for msg in messages:
        print(msg)

    await client.disconnect()  # Отключаемся после работы

with client:
    client.loop.run_until_complete(main())
"""