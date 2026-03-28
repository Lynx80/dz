import asyncio
import os
import sys
from database import Database
from parser import ParserService

async def main():
    db = Database()
    parser = ParserService()
    
    user_id = 999999
    # Предварительно заполняем профиль для теста
    db.create_user(user_id)
    db.update_user(user_id, first_name="Тест", last_name="Тестович", grade="10")
    
    url = "https://videouroki.net/tests/628623254/"
    
    print(f"START Solving test: {url}")
    
    async def update_status(text):
        print(f"Status: {text}")

    async def send_screenshot(path, label):
        print(f"Screenshot: {label} -> {path}")

    try:
        result = await parser.solve_test(user_id, url, update_status, send_screenshot)
        print(f"Финальный результат: {result}")
    except Exception as e:
        print(f"Ошибка при выполнении: {e}")

if __name__ == "__main__":
    asyncio.run(main())
