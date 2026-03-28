import asyncio
import os
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv

load_dotenv()

async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    proxy = os.getenv("TELEGRAM_PROXY")
    
    print(f"Checking token: {token}")
    print(f"Using proxy: {proxy}")
    
    if proxy:
        session = AiohttpSession(proxy=proxy)
        bot = Bot(token=token, session=session)
    else:
        bot = Bot(token=token)
        
    try:
        me = await bot.get_me()
        print(f"Success! Bot: @{me.username}")
    except Exception as e:
        print(f"Failed: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
