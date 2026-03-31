"""
Проходит тест на videouroki.net в видимом браузере.
Запуск: python3 run_test.py <URL>
"""
import asyncio
import sys
import os
import base64
import json
import re
import httpx
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

URL = sys.argv[1] if len(sys.argv) > 1 else "https://videouroki.net/tests/939872999/"
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"

PROMPT = """Ты помогаешь ответить на вопрос теста.
На изображении — вопрос с вариантами ответов.
Ответь ТОЛЬКО JSON: {{"answer_index": 0}} где answer_index — индекс правильного ответа (0-based).
Если вопрос без вариантов (текстовый ввод) — {{"answer_text": "ответ"}}.
Без пояснений, только JSON."""

async def ask_gemini(screenshot_bytes: bytes, question_text: str = "") -> dict:
    img_b64 = base64.b64encode(screenshot_bytes).decode()
    payload = {
        "contents": [{
            "parts": [
                {"text": PROMPT + (f"\n\nВопрос: {question_text}" if question_text else "")},
                {"inline_data": {"mime_type": "image/png", "data": img_b64}}
            ]
        }]
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(GEMINI_URL, json=payload)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        text = re.sub(r"```json|```", "", text).strip()
        return json.loads(text)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--start-maximized"]
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
            locale="ru-RU",
        )
        page = await ctx.new_page()

        print(f"[→] Открываю {URL}")
        await page.goto(URL, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # ── Шаг 1: заполнить форму с данными ───────────────────────────
        print("[→] Заполняю форму...")
        try:
            await page.fill('input[placeholder*="амили"], input[name*="last"], input[id*="last"]', "Иванов")
        except: pass
        try:
            await page.fill('input[placeholder*="мя"], input[name*="first"], input[id*="first"]', "Иван")
        except: pass
        try:
            await page.fill('input[placeholder*="ласс"], input[name*="class"], input[id*="class"]', "11 А")
        except: pass

        # Кнопка начать
        start_btn = await page.query_selector('button[type=submit], button:has-text("Начать"), .btn-start, input[type=submit]')
        if start_btn:
            await start_btn.click()
            print("[✓] Тест начат")
            await page.wait_for_timeout(2000)
        else:
            print("[!] Кнопка старта не найдена, пробую Enter")
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2000)

        # ── Шаг 2: проходим вопросы ─────────────────────────────────────
        question_num = 0
        while True:
            await page.wait_for_timeout(1500)

            # Проверяем не закончился ли тест
            result_el = await page.query_selector('[class*=result], [class*=Result], [class*=finish], .test-result')
            if result_el:
                result_text = await result_el.inner_text()
                print(f"\n[✓] ТЕСТ ЗАВЕРШЁН!\n{result_text}")
                break

            # Скриншот текущего состояния
            screenshot = await page.screenshot()

            # Текст вопроса
            q_text = ""
            for sel in ['[class*=question-text]', '[class*=questionText]', '.question', 'h3', 'h2']:
                el = await page.query_selector(sel)
                if el:
                    q_text = await el.inner_text()
                    if q_text.strip():
                        break

            question_num += 1
            print(f"[{question_num}] Вопрос: {q_text[:80]}...")

            # Спрашиваем Gemini
            try:
                result = await ask_gemini(screenshot, q_text)
                print(f"    Gemini ответ: {result}")
            except Exception as e:
                print(f"    [!] Gemini ошибка: {e}, пропускаю")
                result = {}

            # Кликаем нужный вариант
            if "answer_index" in result:
                idx = result["answer_index"]
                # Собираем все радио/чекбоксы и лейблы
                options = await page.query_selector_all(
                    'input[type=radio], input[type=checkbox], '
                    '[class*=answer-item], [class*=answerItem], '
                    '[class*=variant], li.answer, .answer-option'
                )
                if options and idx < len(options):
                    await options[idx].scroll_into_view_if_needed()
                    await options[idx].click()
                    print(f"    [✓] Выбран вариант {idx}")
                else:
                    print(f"    [!] Вариантов {len(options)}, запрошен {idx}")

            elif "answer_text" in result:
                text_input = await page.query_selector('input[type=text], textarea')
                if text_input:
                    await text_input.fill(result["answer_text"])
                    print(f"    [✓] Введён текст: {result['answer_text']}")

            await page.wait_for_timeout(800)

            # Кнопка "Следующий" / "Ответить"
            next_btn = None
            for sel in [
                'button:has-text("Следующий")',
                'button:has-text("Далее")',
                'button:has-text("Ответить")',
                'button:has-text("Next")',
                '.btn-next', '.next-btn',
                'button[type=submit]',
            ]:
                next_btn = await page.query_selector(sel)
                if next_btn:
                    break

            if next_btn:
                await next_btn.click()
                await page.wait_for_timeout(1000)
            else:
                # Возможно последний вопрос — ищем "Завершить"
                finish_btn = await page.query_selector('button:has-text("Завершить"), button:has-text("Finish"), .btn-finish')
                if finish_btn:
                    await finish_btn.click()
                    print("[→] Нажал Завершить")
                    await page.wait_for_timeout(3000)
                    break
                else:
                    print("[!] Кнопка не найдена, жду 3 сек...")
                    await page.wait_for_timeout(3000)
                    # Проверяем не изменилась ли страница
                    question_num_check = question_num
                    if question_num_check >= 10:
                        break

        print("\n[✓] Готово. Браузер остаётся открытым.")
        await asyncio.sleep(30)  # Держим браузер открытым 30 сек
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
