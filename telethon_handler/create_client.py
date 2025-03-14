from telethon.sync import TelegramClient
from config import config

client = TelegramClient("/root/CM/my_session", config.telethon_id, config.telethon_hash)
