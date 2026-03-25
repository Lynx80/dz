import httpx
from typing import Optional, Dict

class SchoolAPI:
    def __init__(self, token: str, region: str = "mos"):
        self.token = token
        self.region = region
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }

    async def get_profile(self) -> Optional[Dict]:
        """Получение профиля через Playwright для обхода блокировок"""
        from playwright.async_api import async_playwright
        
        endpoints = [
            "https://school.mos.ru/api/family/web/v1/profile",
            "https://authedu.mosreg.ru/v2/profile"
        ]
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            # Явно не используем прокси для запросов к школе
            context = await browser.new_context(user_agent="Mozilla/5.0", proxy={"server": "direct://"})
            page = await context.new_page()
            
            # Устанавливаем заголовок авторизации через перехват запросов или просто через API контекста
            await context.set_extra_http_headers(self.headers)
            
            for url in endpoints:
                try:
                    print(f"Playwright: fetching {url}")
                    resp = await page.goto(url, wait_until="networkidle", timeout=20000)
                    if resp and resp.status == 200:
                        data = await resp.json()
                        print(f"Playwright success: {url}")
                        await browser.close()
                        return {
                            "first_name": data.get("first_name") or data.get("firstName") or "Не указано",
                            "last_name": data.get("last_name") or data.get("lastName") or "Не указано",
                            "class_name": data.get("class_name") or data.get("className") or "Не указано"
                        }
                    else:
                        print(f"Playwright: {url} status {resp.status if resp else 'None'}")
                except Exception as e:
                    print(f"Playwright error from {url}: {e}")
            
            await browser.close()
        return None

    async def get_tests(self) -> list:
        """Получение списка ЦДЗ тестов (без прокси)"""
        url = "https://school.mos.ru/api/family/web/v1/diary" if self.region == "mos" else "https://authedu.mosreg.ru/v2/diary"
        try:
            async with httpx.AsyncClient(proxies={}) as client:
                resp = await client.get(url, headers=self.headers, timeout=20)
                if resp.status_code == 200:
                    # Здесь должна быть логика извлечения тестов из дневника
                    return resp.json().get("tests", [])
                return []
        except Exception:
            return []
