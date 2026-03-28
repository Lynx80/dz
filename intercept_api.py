import asyncio
import json
from playwright.async_api import async_playwright
import os

async def intercept_diary():
    # Use existing session if possible
    session_dir = os.path.join(os.getcwd(), 'sessions', 'user_default')
    
    async with async_playwright() as p:
        if os.path.exists(session_dir):
            context = await p.chromium.launch_persistent_context(
                session_dir,
                headless=True,
                viewport={'width': 1280, 'height': 800}
            )
        else:
            print("No session found. Please login first.")
            return

        page = context.pages[0] if context.pages else await context.new_page()
        
        captured_data = []

        async def handle_response(response):
            if "api" in response.url and "json" in response.headers.get("content-type", ""):
                try:
                    data = await response.json()
                    captured_data.append({
                        "url": response.url,
                        "data": data
                    })
                except:
                    pass

        page.on("response", handle_response)
        
        print("Navigating to diary...")
        # Try a few common diary URLs
        await page.goto("https://myschool.mosreg.ru/diary/schedule")
        await asyncio.sleep(5) # Wait for loads
        
        await page.goto("https://myschool.mosreg.ru/diary/homework")
        await asyncio.sleep(5)

        with open('captured_api.json', 'w', encoding='utf-8') as f:
            json.dump(captured_data, f, ensure_ascii=False, indent=2)
        
        print(f"Captured {len(captured_data)} API responses to captured_api.json")
        await context.close()

if __name__ == "__main__":
    asyncio.run(intercept_diary())
