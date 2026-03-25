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
        """Получение данных профиля ученика"""
        url = "https://school.mos.ru/api/family/web/v1/profile" if self.region == "mos" else "https://authedu.mosreg.ru/v2/profile"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self.headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    # Упрощенный пример маппинга данных
                    return {
                        "first_name": data.get("first_name", "Не указано"),
                        "last_name": data.get("last_name", "Не указано"),
                        "class_name": data.get("class_name", "Не указано")
                    }
                return None
        except Exception as e:
            print(f"Error fetching profile: {e}")
            return None

    async def get_tests(self) -> list:
        """Получение списка ЦДЗ тестов"""
        url = "https://school.mos.ru/api/family/web/v1/diary" if self.region == "mos" else "https://authedu.mosreg.ru/v2/diary"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self.headers, timeout=10)
                if resp.status_code == 200:
                    # Здесь должна быть логика извлечения тестов из дневника
                    return resp.json().get("tests", [])
                return []
        except Exception:
            return []
