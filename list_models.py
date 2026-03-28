import asyncio
import aiohttp
import os
from dotenv import load_dotenv
from aiohttp_socks import ProxyConnector

load_dotenv()

async def main():
    api_key = os.getenv("GEMINI_API_KEY")
    proxy = os.getenv("TELEGRAM_PROXY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    
    connector = ProxyConnector.from_url(proxy) if proxy else None
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get(url) as resp:
            print(f"Status: {resp.status}")
            data = await resp.json()
            if 'models' in data:
                for m in data['models']:
                    print(f"- {m['name']} (Supported: {m['supportedGenerationMethods']})")
            else:
                print(data)

if __name__ == "__main__":
    asyncio.run(main())
