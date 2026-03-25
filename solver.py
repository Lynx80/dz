import asyncio
from playwright.async_api import async_playwright
import logging
from services.ai_helper import AIHelper

logger = logging.getLogger(__name__)

class TestSolver:
    def __init__(self, token: str, test_url: str):
        self.token = token
        self.test_url = test_url
        self.ai = AIHelper()

    async def solve(self, status_callback=None):
        """Определение типа сайта и запуск соответствующего солвера"""
        if "videouroki.net" in self.test_url:
            return await self.solve_videouroki(status_callback)
        else:
            return await self.solve_mesh(status_callback)

    async def solve_videouroki(self, status_callback):
        """Специфическая логика для Videouroki.net"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent="Mozilla/5.0")
            page = await context.new_page()
            
            try:
                if status_callback: await status_callback("🌐 Загрузка Videouroki...")
                await page.goto(self.test_url, wait_until="networkidle")
                
                # Авторизация/Вход в тест (ввод имени)
                inputs = await page.query_selector_all("input[type='text']")
                for inp in inputs:
                    await inp.fill("Ученик")
                await page.click("input.btn.green") # Кнопка Начать тест
                await asyncio.sleep(2)

                while True:
                    # Проверка, не закончился ли тест
                    if await page.query_selector(".test-results"):
                        if status_callback: await status_callback("🏁 Тест завершен!")
                        break
                    
                    # Парсинг вопроса
                    question_text = await page.inner_text("h3")
                    if status_callback: await status_callback(f"🤔 Решаю: {question_text[:30]}...")
                    
                    # Обработка разных типов вопросов
                    # 1. Если есть сопоставление (dropdowns)
                    dropdown_wrappers = await page.query_selector_all(".el-select")
                    if dropdown_wrappers:
                        # Получаем текст категорий (например: 1. Война, 2. Мир)
                        categories_text = await page.inner_text(".quest-item-text") # Или другой контейнер с описанием
                        
                        for wrapper in dropdown_wrappers:
                            # Получаем текст конкретного пункта для сопоставления
                            item_text = await wrapper.evaluate("el => el.parentElement.innerText")
                            
                            ai_answer = await self.ai.get_answer(
                                f"Сопоставь пункт '{item_text}' с категориями: {categories_text}",
                                ["1", "2"] # В реале парсить количество категорий
                            )
                            
                            # Приводим ответ ИИ к числу (индексу)
                            target_index = "".join(filter(str.isdigit, ai_answer))
                            if not target_index: target_index = "1"
                            
                            # Кликаем на дропдаун
                            input_el = await wrapper.query_selector("input.el-input__inner")
                            await input_el.click()
                            await asyncio.sleep(1)
                            
                            # Выбираем нужный пункт из списка li по тексту (номеру)
                            options = await page.query_selector_all("li.el-select-dropdown__item")
                            for opt in options:
                                opt_text = await opt.inner_text()
                                if target_index in opt_text:
                                    await opt.click()
                                    await asyncio.sleep(0.5)
                                    break
                    else:
                        # 2. Обычный выбор (Радио/Чекбоксы)
                        options_elements = await page.query_selector_all("label.el-radio, label.el-checkbox")
                        options_texts = [await el.inner_text() for el in options_elements]
                        
                        ai_answer = await self.ai.get_answer(question_text, options_texts)
                        
                        # Кликаем по элементу, текст которого похож на ответ ИИ
                        for el, txt in zip(options_elements, options_texts):
                            if ai_answer.lower() in txt.lower():
                                await el.click()
                                break
                    
                    # Нажимаем Далее
                    next_btn = await page.query_selector("button.btn:has-text('Далее')")
                    if next_btn:
                        await next_btn.click()
                        await asyncio.sleep(2)
                    else:
                        break
                
                return True
            except Exception as e:
                logger.error(f"Videouroki Error: {e}")
                return False
            finally:
                await browser.close()

    async def solve_mesh(self, status_callback):
        """Логика для МЭШ (базовая)"""
        # (Код из предыдущей версии)
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent="Mozilla/5.0")
            await context.add_cookies([{"name": "auth_token", "value": self.token, "domain": "school.mos.ru", "path": "/"}])
            page = await context.new_page()
            try:
                await page.goto(self.test_url, timeout=60000)
                if status_callback: await status_callback("🤖 Решаю МЭШ тест...")
                await asyncio.sleep(5)
                return True
            except Exception:
                return False
            finally:
                await browser.close()
