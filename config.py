from dotenv import load_dotenv
import os

load_dotenv()

class Config:
    def __init__(self):
        # Чтение переменных окружения
        self.tg_bot_token = os.getenv('BOT_API_TOKEN')
        self.db_user = os.getenv('DB_USER')
        self.db_password = os.getenv('DB_PASSWORD')
        self.trading_group_id = int(os.getenv('TRADING_GROUP_ID'))
        self.telethon_id = int(os.getenv('TELETHON_ID'))
        self.telethon_hash = os.getenv('TELETHON_HASH')
        self.deepseek_api = os.getenv('DEEPSEEK_API')
        self.telethon_session = os.getenv('TELETHON_SESSION')

config = Config()

