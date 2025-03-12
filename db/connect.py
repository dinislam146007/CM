import asyncpg
from config import config


async def connect() -> asyncpg.Connection:
    return await asyncpg.connect(
        host="localhost",
        port=5432,
        user=config.db_user,
        password=config.db_password,
        database="trading_db"
    )
