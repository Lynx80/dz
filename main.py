import asyncio
import logging
import sys
import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession

from config import API_TOKEN, PID_FILE, PROXY_URL
from database.db import Database
from services.parser import ParserService, MosregAuthError
from handlers import common, homework, solve, settings, profile
from utils.pid import create_pid_file, remove_pid_file

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

async def token_refresher_task(db: Database, parser: ParserService):
    """Задача для автоматического обновления токенов каждые 40 минут."""
    while True:
        try:
            logger.info("Starting background token refresh cycle...")
            users = await db.get_all_users_with_tokens()
            for u in users:
                try:
                    new_token = await parser.refresh_token(u['token_mos'])
                    if new_token:
                        await db.update_user(u['user_id'], token_mos=new_token)
                        logger.info(f"Refreshed token for user {u['user_id']}")
                except MosregAuthError:
                    logger.warning(f"Token for user {u['user_id']} is dead.")
                except Exception as e:
                    logger.error(f"Error refreshing for {u['user_id']}: {e}")
                
                await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Refresher task error: {e}")
        
        await asyncio.sleep(40 * 60)

async def main():
    if not create_pid_file(PID_FILE):
        return

    # Initialize DB
    db = Database()
    await db._create_tables()

    # Initialize Bot & Dispatcher
    if PROXY_URL:
        logger.info(f"Using proxy: {PROXY_URL}")
        session = AiohttpSession(proxy=PROXY_URL)
        bot = Bot(token=API_TOKEN, session=session)
    else:
        bot = Bot(token=API_TOKEN)
        
    dp = Dispatcher(storage=MemoryStorage())

    # Initialize Service
    parser = ParserService()

    # Register Routers
    dp.include_router(common.router)
    dp.include_router(homework.router)
    dp.include_router(solve.router)
    dp.include_router(settings.router)
    dp.include_router(profile.router)

    async with aiohttp.ClientSession() as shared_session:
        # Link shared session to parser
        parser.session = shared_session
        
        # Start background tasks
        refresher = asyncio.create_task(token_refresher_task(db, parser))
        
        try:
            logger.info("Bot is starting polling...")
            await dp.start_polling(bot)
        finally:
            refresher.cancel()
            await bot.session.close()
            remove_pid_file(PID_FILE)
            logger.info("Bot stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot manually stopped.")
