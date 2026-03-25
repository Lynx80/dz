import asyncio
import os
import logging
import re
import base64
import json
import aiohttp
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from ai import AIService
from database import Database

logger = logging.getLogger(__name__)

class ParserService:
    def __init__(self):
        self.ai = AIService()
        self.db = Database()
        self.base_headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-A525F Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Client-Type': 'diary-mobile',
            'X-Mes-Subsystem': 'familymp'
        }

    def decode_jwt(self, token):
        """Декодирует JWT payload."""
        try:
            parts = token.split('.')
            if len(parts) < 2: return {}
            payload = parts[1]
            padded = payload + '=' * (4 - len(payload) % 4)
            decoded = base64.b64decode(padded).decode('utf-8')
            return json.loads(decoded)
        except Exception as e:
            logger.error(f"JWT decode error: {e}")
            return {}

    async def refresh_token(self, access_token):
        """Обновляет токен через v2/token/refresh."""
        url = "https://authedu.mosreg.ru/v2/token/refresh"
        headers = self.base_headers.copy()
        headers['Authorization'] = f'Bearer {access_token}'
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers, timeout=15) as resp:
                    if resp.status == 200:
                        new_token = await resp.text()
                        new_token = new_token.strip().strip('"')
                        if new_token.startswith('eyJ'):
                            logger.info("Token refreshed via v2/token/refresh")
                            return new_token
            except Exception as e:
                logger.error(f"Token refresh error: {e}")
        return None

    async def _activate_session(self, access_token):
        """
        Обязательная активация сессии через profile_info (handshake).
        Без этого API возвращает 403 Forbidden.
        """
        url = "https://myschool.mosreg.ru/acl/api/users/profile_info"
        headers = self.base_headers.copy()
        headers['auth-token'] = access_token
        headers['Authorization'] = f'Bearer {access_token}'
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers, timeout=15) as resp:
                    logger.info(f"Session activation: status={resp.status}")
                    if resp.status == 200:
                        data = await resp.json()
                        logger.info(f"Session activated")
                        return data
            except Exception as e:
                logger.error(f"Session activation error: {e}")
        return None

    async def fetch_mosreg_profile(self, access_token):
        """
        Получает профиль через API.
        1. Активация сессии (handshake)
        2. Запрос полных данных (имя, класс) через authedu.mosreg.ru/api/family/mobile/v1/profile
        """
        # Шаг 1: Активация сессии (обязательно для 200 OK на других эндпоинтах)
        activation = await self._activate_session(access_token)
        
        # Шаг 2: Получение полных данных
        # Эндпоинты на authedu.mosreg.ru обычно более стабильны для мобильных токенов
        profile_url = "https://authedu.mosreg.ru/api/family/mobile/v1/profile"
        headers = self.base_headers.copy()
        headers['Authorization'] = f'Bearer {access_token}'
        headers['auth-token'] = access_token
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(profile_url, headers=headers, timeout=15) as resp:
                    logger.info(f"Full profile status={resp.status}")
                    if resp.status == 200:
                        data = await resp.json()
                        logger.info(f"Full profile data received")
                        children = data.get('children', [])
                        if children:
                            child = children[0]
                            return {
                                "first_name": child.get('first_name') or child.get('firstname', 'Ученик'),
                                "last_name": child.get('last_name') or child.get('lastname', ''),
                                "grade": str(child.get('class_name') or ''),
                                "student_id": str(child.get('id', ''))
                            }
                    elif resp.status == 401:
                        new_token = await self.refresh_token(access_token)
                        if new_token: return await self.fetch_mosreg_profile(new_token)
            except Exception as e:
                logger.error(f"Fetch profile error: {e}")

        # Fallback: пробуем достать хоть что-то из активации
        if activation and isinstance(activation, list) and len(activation) > 0:
            p = activation[0]
            user_info = p.get('user', {})
            return {
                "first_name": p.get('first_name') or user_info.get('first_name') or 'Ученик',
                "last_name": p.get('last_name') or user_info.get('last_name') or '',
                "grade": str(p.get('class_name') or ''),
                "student_id": str(p.get('id') or p.get('person_id', ''))
            }
        
        return None

    async def get_mosreg_homework(self, access_token, student_id, date_str=None):
        """
        Получает ЦДЗ через eventcalendar API.
        """
        if not student_id: return []
        if not date_str: date_str = datetime.now().strftime('%Y-%m-%d')
        begin_date = date_str
        end_date = (datetime.strptime(date_str, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        
        url = (f"https://authedu.mosreg.ru/api/eventcalendar/v1/api/events"
               f"?person_ids={student_id}&begin_date={begin_date}&end_date={end_date}&expand=homework")
        headers = self.base_headers.copy()
        headers['Authorization'] = f'Bearer {access_token}'
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        homeworks = []
                        events = data.get('response', [])
                        for event in events:
                            subject = event.get('subject_name') or event.get('title', 'Без предмета')
                            hw_list = event.get('homework', [])
                            if not isinstance(hw_list, list): hw_list = [hw_list] if hw_list else []
                            
                            for hw in hw_list:
                                desc = hw.get('description', '') or hw.get('text', '')
                                link = None
                                # Ищем ссылки в материалах
                                materials = hw.get('materials', [])
                                for m in materials:
                                    for item in m.get('items', []):
                                        if item.get('link'): link = item.get('link'); break
                                    if link: break
                                    
                                if not link: # Ищем в тексте
                                    urls = re.findall(r'https?://[^\s<>"]+', desc)
                                    if urls: link = urls[0]
                                    
                                if desc or link:
                                    homeworks.append({
                                        "subject": subject, "description": desc,
                                        "date": event.get('start_at', date_str)[:10], "link": link
                                    })
                        return homeworks
            except Exception as e:
                logger.error(f"Homework error: {e}")
        return await self._get_homework_fallback(access_token, student_id, date_str)

    async def _get_homework_fallback(self, access_token, student_id, date_str):
        """Fallback: homeworks/short через authedu.mosreg.ru"""
        end_date = (datetime.strptime(date_str, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        url = (f"https://authedu.mosreg.ru/api/family/mobile/v1/homeworks/short"
               f"?student_id={student_id}&from={date_str}&to={end_date}")
        headers = self.base_headers.copy()
        headers['Authorization'] = f'Bearer {access_token}'
        headers['auth-token'] = access_token
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers, timeout=15) as resp:
                    logger.info(f"Homework fallback status={resp.status}")
                    if resp.status == 200:
                        data = await resp.json()
                        logger.info(f"Homework fallback data: {json.dumps(data, ensure_ascii=False)[:300]}")
                        homeworks = []
                        payload = data.get('payload', data) if isinstance(data, dict) else data
                        if isinstance(payload, list):
                            for hw in payload:
                                subject = hw.get('subject_name', 'Без предмета')
                                desc = hw.get('description', '')
                                for material in hw.get('materials', []):
                                    for item in material.get('items', []):
                                        link = item.get('link')
                                        if link:
                                            homeworks.append({
                                                "subject": subject, "description": desc,
                                                "date": hw.get('date', date_str), "link": link
                                            })
                                if not any(m.get('items') for m in hw.get('materials', [])):
                                    homeworks.append({
                                        "subject": subject, "description": desc,
                                        "date": hw.get('date', date_str), "link": None
                                    })
                        return homeworks
            except Exception as e:
                logger.error(f"Homework fallback error: {e}")
        return []

    async def fetch_mesh_profile(self, token):
        url = "https://school.mos.ru/api/family/v1/profile"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "X-Mes-Subsystem": "familymp"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        profile = data.get("children", [{}])[0]
                        return {
                            "first_name": profile.get("first_name"),
                            "last_name": profile.get("last_name"),
                            "grade": str(profile.get("class_name", "")).split()[0]
                        }
            except: pass
        return None

    async def solve_test(self, user_id, test_url, status_callback=None, screenshot_callback=None):
        user = self.db.get_user(user_id)
        if not user: return "Ошибка: Профиль не найден."
        if "videouroki.net" in test_url:
            return await self._solve_videouroki(user, test_url, status_callback, screenshot_callback)
        elif "mesh.mos.ru" in test_url or "school.mos.ru" in test_url:
            return await self._solve_mesh(user, test_url, status_callback, screenshot_callback)
        else:
            return "Ошибка: Данная платформа пока не поддерживается."

    async def _solve_videouroki(self, user, test_url, status_callback, screenshot_callback):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={'width': 1280, 'height': 720})
            page = await context.new_page()
            try:
                if status_callback: await status_callback("🌐 Загрузка Videouroki...")
                await page.goto(test_url, timeout=60000)
                await asyncio.sleep(2)
                inputs = await page.query_selector_all("input[type='text']")
                if inputs:
                    if len(inputs) >= 3:
                        await inputs[0].fill(user.get('last_name') or "Ученик")
                        await inputs[1].fill(user.get('first_name') or "Пользователь")
                        await inputs[2].fill(user.get('grade') or "10")
                    else:
                        await inputs[0].fill(f"{user.get('last_name', '')} {user.get('first_name', 'Ученик')}".strip())
                    await page.click("button.btn.green, input.btn.green, .btn-start")
                    await asyncio.sleep(2)
                q_num = 0
                while True:
                    if await page.query_selector(".test-results, .final-score"): break
                    q_num += 1
                    question_elem = await page.wait_for_selector("h3, .v-question-text, .quest-text", timeout=10000)
                    if not question_elem: break
                    question_text = await question_elem.inner_text()
                    if status_callback: await status_callback(f"🤔 Решаю вопрос {q_num}...")
                    options_elements = await page.query_selector_all("label.el-radio, label.el-checkbox, .v-answer-item")
                    options_texts = [await el.inner_text() for el in options_elements]
                    if q_num > 1: await asyncio.sleep(40)
                    ai_res = await self.ai.get_answer(question_text, options_texts)
                    ans_val = ai_res.get("answer")
                    idx = self._match_index(ans_val, options_texts)
                    if idx != -1: await options_elements[idx].click()
                    next_btn = await page.query_selector("button:has-text('Далее'), .btn-next")
                    if next_btn: await next_btn.click()
                    else: await page.keyboard.press("Enter")
                    await asyncio.sleep(1.5)
                result_text = await page.inner_text(".test-results, .final-score")
                self.db.add_test_score(user['user_id'], test_url, result_text)
                return f"✅ Готово! Результат: {result_text}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
            finally:
                await browser.close()

    async def _solve_mesh(self, user, test_url, status_callback, screenshot_callback):
        return "⚠️ Модуль МЭШ временно недоступен."

    def _match_index(self, ai_val, options):
        if isinstance(ai_val, int):
            return ai_val - 1 if 0 < ai_val <= len(options) else -1
        val_str = str(ai_val).lower().strip()
        for i, opt in enumerate(options):
            if val_str in opt.lower(): return i
        return -1
