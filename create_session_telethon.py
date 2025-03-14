from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from config import config

with TelegramClient(StringSession(), config.telethon_id, config.telethon_hash) as client:
    print(client.session.save())
