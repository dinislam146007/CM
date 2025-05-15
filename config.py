from dotenv import load_dotenv
import os

load_dotenv()

class Config:
    def __init__(self):
        # Чтение переменных окружения
        self.tg_bot_token = os.getenv('BOT_API_TOKEN')
        self.db_user = os.getenv('DB_USER')
        self.db_password = os.getenv('DB_PASSWORD')
        self.trading_group_id = int(os.getenv('TRADING_GROUP_ID', '-1002467387559'))
        self.public_channel_id = int(os.getenv('PUBLIC_CHANNEL_ID', '0'))
        self.telethon_id = int(os.getenv('TELETHON_ID'))
        self.telethon_hash = os.getenv('TELETHON_HASH')
        self.deepseek_api = os.getenv('DEEPSEEK_API')
        self.telethon_session = os.getenv('TELETHON_SESSION')
        self.ai_tokens = ['BTCUSDT', 'DOGEUSDT', 'ETHUSDT', 'LTCUSDT', 'XRPUSDT', 'SOLUSDT', 'TRXUSDT']

config = Config()

