import asyncio
import os
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv
from database.db_service import init_db
from handlers import start, auth, profile, tests, solve

# Настройка логирования
logging.basicConfig(level=logging.INFO)

async def main():
    load_dotenv()
    
    # Инициализация БД
    await init_db()
    
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("Error: TELEGRAM_BOT_TOKEN not found in .env")
        return

    proxy_url = os.getenv("TELEGRAM_PROXY")
    session = AiohttpSession(proxy=proxy_url) if proxy_url else None
    bot = Bot(token=bot_token, session=session)
    dp = Dispatcher()

    # Регистрация роутеров
    dp.include_router(start.router)
    dp.include_router(auth.router)
    dp.include_router(profile.router)
    dp.include_router(tests.router)
    dp.include_router(solve.router)

    print("Bot started and ready to work!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен.")
