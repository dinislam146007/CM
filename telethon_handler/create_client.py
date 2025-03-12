from telethon.sync import TelegramClient
from config import config

client = TelegramClient("my_session", config.telethon_id, config.telethon_hash)
