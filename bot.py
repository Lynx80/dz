import asyncio
import logging
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession

from database.db import Database
from services.parser import ParserService, MosregAuthError

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Инициализация переменных
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PROXY_URL = os.getenv("TELEGRAM_PROXY")

# Инициализация сессии и бота
if PROXY_URL:
    logger.info(f"Using proxy: {PROXY_URL}")
    session = AiohttpSession(proxy=PROXY_URL)
    bot = Bot(token=API_TOKEN, session=session)
else:
    bot = Bot(token=API_TOKEN)

# Инициализация диспетчера и сервисов
dp = Dispatcher(storage=MemoryStorage())
db = Database()
parser = ParserService()

# ─── РЕГИСТРАЦИЯ РОУТЕРОВ ───
from handlers import start, auth, homework, solve, profile, settings, common

dp.include_router(start.router)
dp.include_router(auth.router)
dp.include_router(homework.router)
dp.include_router(solve.router)
dp.include_router(profile.router)
dp.include_router(settings.router)
dp.include_router(common.router)

# ─── ФОНОВЫЕ ЗАДАЧИ ───

async def token_refresher_task(parser_service):
    """Фоновая задача для автоматического обновления токенов каждые 40 минут."""
    while True:
        try:
            logger.info("Starting background token refresh cycle...")
            users = await db.get_all_users_with_tokens()
            for u in users:
                try:
                    new_token = await parser_service.refresh_token(u['token_mos'])
                    if new_token:
                        await db.update_user(u['user_id'], token_mos=new_token)
                        logger.info(f"Refreshed token for user {u['user_id']}")
                    else:
                        logger.warning(f"Could not refresh token for user {u['user_id']} (no response)")
                except MosregAuthError:
                    logger.warning(f"Token for user {u['user_id']} is dead.")
                except Exception as e:
                    logger.error(f"Error refreshing token for {u['user_id']}: {e}")
                
                await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Refresher task error: {e}")
        
        await asyncio.sleep(40 * 60)

# ─── ЗАПУСК ───

PID_FILE = "bot.pid"

def create_pid_file():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                pid = f.read().strip()
            import subprocess
            output = subprocess.check_output(f'tasklist /FI "PID eq {pid}"', shell=True).decode('cp866')
            if pid in output:
                logger.error(f"Bot is already running (PID: {pid}). Exiting.")
                return False
        except: pass
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
    return True

def remove_pid_file():
    if os.path.exists(PID_FILE):
        try: os.remove(PID_FILE)
        except: pass

async def main():
    if not create_pid_file():
        return

    logger.info("Bot starting with modular architecture...")
    
    import aiohttp
    async with aiohttp.ClientSession() as shared_session:
        # Привязываем общую сессию к парсеру
        parser.session = shared_session
        
        # Запуск фоновых задач
        refresher = asyncio.create_task(token_refresher_task(parser))
        
        try:
            await dp.start_polling(bot)
        finally:
            refresher.cancel()
            remove_pid_file()
            logger.info("Bot stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        remove_pid_file()
