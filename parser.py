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

class MosregAuthError(Exception):
    """Исключение при ошибке авторизации (401)."""
    pass

class ParserService:
    def __init__(self, session=None):
        self.ai = AIService()
        self.db = Database()
        self.session = session
        self._cache = {} # (key): {data: ..., expiry: ...}
        self.base_headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-A525F Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Client-Type': 'diary-mobile',
            'X-Mes-Subsystem': 'family'
        }

    def _get_from_cache(self, key):
        if key in self._cache:
            entry = self._cache[key]
            if datetime.now() < entry['expiry']:
                logger.info(f"Using cached data for {key}")
                return entry['data']
            else:
                del self._cache[key]
        return None

    def _set_to_cache(self, key, data, ttl_seconds=600):
        self._cache[key] = {
            'data': data,
            'expiry': datetime.now() + timedelta(seconds=ttl_seconds)
        }

    async def _get_session(self):
        if self.session and not self.session.closed:
            return self.session
        self.session = aiohttp.ClientSession()
        return self.session

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
        headers['auth-token'] = access_token
        session = await self._get_session()
        try:
            async with session.get(url, headers=headers, timeout=15) as resp:
                if resp.status in [200, 201]:
                    new_token = await resp.text()
                    new_token = new_token.strip().strip('"')
                    if new_token.startswith('eyJ'):
                        logger.info("Token refreshed successfully")
                        return new_token
                else:
                    logger.warning(f"Refresh failed: {resp.status}")
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
        return None

    async def _activate_session(self, access_token, subsystem='familymp'):
        """
        Обязательная активация сессии через profile_info (handshake).
        Без этого API возвращает 403 Forbidden.
        """
        headers = self.base_headers.copy()
        # Пробуем разные вариации заголовка токена
        headers['auth-token'] = access_token
        headers['Auth-Token'] = access_token
        
        urls = [
            'https://myschool.mosreg.ru/acl/api/users/profile_info',
            'https://myschool.mosreg.ru/acl/api/v1/auth/activate',
            'https://api.myschool.mosreg.ru/educational/v1/profile',
            'https://authedu.mosreg.ru/api/family/web/v1/profile',
            'https://authedu.mosreg.ru/api/profile/v2/handshake',
            'https://authedu.mosreg.ru/api/family/mobile/v1/profile'
        ]
        
        headers['Authorization'] = f'Bearer {access_token}'
        headers['X-Mes-Subsystem'] = subsystem
        session = await self._get_session()
        
        for url in urls:
            try:
                # Для web-версии иногда нужен специфический Referer
                if 'family/web' in url:
                    headers['Referer'] = 'https://myschool.mosreg.ru/'
                
                async with session.get(url, headers=headers, timeout=10) as resp:
                    logger.info(f"Handshake [{subsystem}] @ {url}: status={resp.status}")
                    if resp.status == 200:
                        return await resp.json() if "application/json" in resp.headers.get("Content-Type", "").lower() else {"status":"ok"}
            except Exception as e:
                logger.error(f"Handshake error [{subsystem}] @ {url}: {e}")
        return None

    async def fetch_mosreg_profile(self, access_token):
        """
        Получает профиль через API и токен.
        Приоритет: 
        1. Имя из самого токена (JWT) - надежнее всего для ФИО.
        2. Прямой запрос к API профиля для получения класса.
        3. Рукопожатие и повторный запрос через разные subsystems.
        """
        user_info = {"first_name": "", "last_name": "", "grade": "", "student_id": ""}
        
        # Шаг 1: Декодируем JWT для получения имени
        try:
            decoded = self.decode_jwt(access_token)
            if decoded:
                # В JWT обычно лежит полное имя (name или given_name)
                raw_name = decoded.get('name') or decoded.get('given_name') or decoded.get('fname') or decoded.get('first_name')
                if raw_name:
                    parts = str(raw_name).strip().split(' ', 1)
                    if len(parts) > 1:
                        user_info["last_name"] = parts[0]
                        user_info["first_name"] = parts[1]
                    else:
                        user_info["first_name"] = parts[0]
                    logger.info(f"Extracted name from JWT: {user_info['first_name']} {user_info['last_name']}")
                
                # sub обычно содержит ID пользователя
                user_info["student_id"] = str(decoded.get('sub', '') or decoded.get('person_id', ''))
        except Exception as e:
            logger.warning(f"JWT decode error: {e}")

        # Подготовка заголовков
        headers = self.base_headers.copy()
        headers['auth-token'] = access_token
        headers['Authorization'] = f'Bearer {access_token}'
        headers['Access-Token'] = access_token
        headers['Referer'] = 'https://myschool.mosreg.ru/'
        
        session = await self._get_session()
        
        # Шаг 2: Пробуем базовые эндпоинты профиля
        profile_endpoints = [
            ("https://authedu.mosreg.ru/api/family/mobile/v1/profile", "family"),
            ("https://authedu.mosreg.ru/api/family/mobile/v1/profile", "familymp"),
            ("https://authedu.mosreg.ru/api/family/web/v1/profile", "familyweb"),
            ("https://api.myschool.mosreg.ru/family/mobile/v1/profile", "family"),
            ("https://api.myschool.mosreg.ru/family/mobile/v1/profile", "familymp"),
            ("https://api.myschool.mosreg.ru/family/mobile/v1/profile", "educational")
        ]

        # Мы не делаем активацию сразу, а будем делать ее внутри цикла для каждой подсистемы
        activation_data = None

        for url, sub in profile_endpoints:
            headers['X-Mes-Subsystem'] = sub
            try:
                # Сначала активируем подсистему
                res = await self._activate_session(access_token, subsystem=sub)
                if res and not activation_data:
                    activation_data = res
                
                async with session.get(url, headers=headers, timeout=5) as resp:
                    logger.info(f"Profile fetch from {url} [{sub}]: status={resp.status}")
                    if resp.status == 200:
                        if "application/json" in resp.headers.get("Content-Type", "").lower():
                            data = await resp.json()
                            # Ищем в profile и в children[0], объединяем их
                            profile = data.get('profile', {})
                            child = data.get('children', [{}])[0] if data.get('children') else {}
                            
                            # Приоритизируем child, так как там есть группы и школа
                            prof = {**profile, **child}
                            logger.info(f"Merged profile data for user {user_info.get('first_name')}: {list(prof.keys())}")
                            
                            if prof:
                                p = self._parse_profile(prof)
                                # Обновляем данные, не затирая полноту имени из JWT если оно уже есть
                                for k, v in p.items():
                                    if v and (not user_info.get(k) or user_info[k] in ["", "Пользователь"]):
                                        user_info[k] = v
                                logger.info(f"Updated profile data from {url} [{sub}]")
                                if user_info.get('grade'): # Если уже нашли класс, можно не продолжать этот цикл
                                    break
            except Exception as e:
                logger.debug(f"Failed profile fetch at {url} [{sub}]: {e}")

        # Шаг 3: Fallback на данные из активации (если API профиля не ответили)
        if activation_data and isinstance(activation_data, list) and not user_info.get('student_id'):
            for p in activation_data:
                if p.get('type') in ['StudentProfile', 'Learner', 'Profile']:
                    user_info["student_id"] = str(p.get('id') or p.get('person_id') or '')
                    if not user_info["first_name"]:
                        user_info["first_name"] = p.get('first_name') or p.get('firstname') or ''

        # Шаг 4: Если имя все еще не найдено
        if not user_info.get("first_name"):
            user_info["first_name"] = "Пользователь"
            
        if user_info.get("student_id"):
            return user_info
        
        # Если даже ID не нашли, это ошибка
        raise MosregAuthError("Не удалось получить базовые данные профиля. Возможно, токен недействителен.")


    def _parse_profile(self, child_data):
        # Приоритизируем числовой 'id' для Mosreg api/family/mobile
        sid = child_data.get('id') or child_data.get('student_id') or child_data.get('person_id') or ''
        # mesh_id (contingent_guid) часто используется в веб-версии и для ДЗ
        mesh_id = child_data.get('contingent_guid') or child_data.get('mesh_id') or ''
        
        # Поиск класса
        grade = str(child_data.get('class_name') or '')
        if not grade:
            # В familymp класс часто лежит в списке groups
            groups = child_data.get('groups', [])
            if isinstance(groups, list) and len(groups) > 0:
                # Обычно первая группа - это основной класс
                grade = str(groups[0].get('name') or '')

        return {
            "first_name": child_data.get('first_name') or child_data.get('firstname') or '',
            "last_name": child_data.get('last_name') or child_data.get('lastname') or '',
            "grade": grade,
            "student_id": str(sid),
            "mesh_id": str(mesh_id)
        }

    async def get_mosreg_schedule(self, access_token, student_id, date_str, mesh_id=None):
        """Получает расписание через Mosreg API с использованием системы Fallback."""
        cache_key = f"schedule_{student_id}_{date_str}_{mesh_id}"
        cached = self._get_from_cache(cache_key)
        if cached: return cached

        headers = self.base_headers.copy()
        headers['Authorization'] = f'Bearer {access_token}'
        headers['auth-token'] = access_token
        headers['Access-Token'] = access_token
        headers['Referer'] = 'https://myschool.mosreg.ru/'
        
        session = await self._get_session()
        
        # Список эндпоинтов (url, subsystem, id_param, apikey_needed, use_guid)
        endpoints = [
            ("https://api.myschool.mosreg.ru/family/mobile/v1/profile/current/schedule", "familymp", "date", False, False),
            ("https://authedu.mosreg.ru/api/eventcalendar/v1/api/events", "familyweb", "personId", False, False),
            ("https://api.myschool.mosreg.ru/family/mobile/v1/schedule/short", "familymp", "student_id", False, False),
            ("https://api.myschool.mosreg.ru/family/v2/diary", "familymp", "student_id", False, False),
            ("https://authedu.mosreg.ru/api/eventcalendar/v1/api/events", "family", "person_ids", True, True),
            ("https://api.myschool.mosreg.ru/family/mobile/v1/schedule", "familymp", "student_id", False, False)
        ]
        
        all_items = []
        for i, (base_url, sub, id_param, needs_apikey, use_guid) in enumerate(endpoints):
            cur_id = mesh_id if use_guid and mesh_id else student_id
            if not cur_id and id_param != "date": continue

            try:
                # Формируем URL
                if "schedule/short" in base_url:
                    url = f"{base_url}?{id_param}={cur_id}&from={date_str}&to={date_str}"
                elif "eventcalendar" in base_url:
                    begin_label = "begin_date" if id_param == "person_ids" else "beginDate"
                    end_label = "end_date" if id_param == "person_ids" else "endDate"
                    url = f"{base_url}?{id_param}={cur_id}&{begin_label}={date_str}&{end_label}={date_str}&expand=homework,marks,absence_reason_id"
                elif id_param == "date" and "profile/current" in base_url:
                    url = f"{base_url}?date={date_str}"
                else:
                    url = f"{base_url}?{id_param}={cur_id}&date={date_str}"
                
                h = headers.copy()
                h['X-Mes-Subsystem'] = sub
                if needs_apikey:
                    h['apikey'] = '7ef6c62c-7b00-4796-96c6-2c7b00279619'
                
                await self._activate_session(access_token, subsystem=sub)
                
                async with session.get(url, headers=h, timeout=12) as resp:
                    logger.info(f"Schedule fetch [{sub}] {url}: {resp.status}")
                    if resp.status == 200:
                        if "application/json" in resp.headers.get("Content-Type", "").lower():
                            data = await resp.json()
                            events = []
                            if isinstance(data, dict):
                                events = data.get('response') or data.get('data') or data.get('payload') or []
                                if not events and isinstance(data.get('data'), list): events = data['data']
                            elif isinstance(data, list):
                                events = data
                            
                            if events:
                                for ev in events:
                                    subject = ev.get('subject_name') or ev.get('title') or ev.get('subject', {}).get('name', 'Урок')
                                    start = ev.get('start_at') or ev.get('begin_time') or ev.get('start_time') or ev.get('start', '')
                                    end = ev.get('finish_at') or ev.get('end_time') or ev.get('end', '')
                                    
                                    hw_data = ev.get('homework') or []
                                    hw_text = ""
                                    if isinstance(hw_data, list):
                                        hw_text = "; ".join([h.get('description', '') for h in hw_data if h.get('description')])
                                    elif isinstance(hw_data, dict):
                                        hw_text = hw_data.get('description', '')
                                    if not hw_text: hw_text = ev.get('homework_text') or ""
                                    
                                    room = ev.get('room_number') or ev.get('room_name') or '?'
                                    
                                    def format_time(t):
                                        if not t: return ""
                                        t = str(t)
                                        if 'T' in t: return t.split('T')[1][:5]
                                        if ' ' in t: # "2026-03-26 09:00:00"
                                            try: return t.split(' ')[1][:5]
                                            except: pass
                                        if ':' in t:
                                            parts = t.split(':')
                                            if len(parts) >= 2:
                                                hrs = parts[0][-2:].strip().zfill(2)
                                                mns = parts[1][:2].strip().zfill(2)
                                                return f"{hrs}:{mns}"
                                        return t

                                    time_str = f"{format_time(start)}-{format_time(end)}"
                                    lesson_obj = {
                                        'name': subject, 'subject': subject, 'time': time_str,
                                        'hw': hw_text, 'room': room, 'id': ev.get('id') or ev.get('lesson_id')
                                    }
                                    if not any(x['name'] == subject and x['time'] == time_str for x in all_items):
                                        all_items.append(lesson_obj)
                                
                                if all_items:
                                    logger.info(f"Schedule found {len(all_items)} items from {sub}")
                                    break # Нашли уроки, выходим из цикла эндпоинтов
                    elif resp.status == 401 and i == len(endpoints) - 1:
                        raise MosregAuthError("Токен истек")
            except MosregAuthError:
                raise
            except Exception as e:
                logger.error(f"Schedule attempt failed [{sub}]: {e}")
        
        if all_items:
            all_items.sort(key=lambda x: x['time'])
            self._set_to_cache(cache_key, all_items)
            return all_items
        
        # Last resort: try V3 API
        logger.info(f"All standard fallbacks failed for user {student_id}. Trying V3 API.")
        items = await self.get_mosreg_schedule_v3(access_token, student_id, date_str)
        if items: return items

        # ULTIMATE resort: Playwright scraping
        logger.info(f"API methods failed for user {student_id}. Launching Playwright fallback.")
        return await self.get_mosreg_schedule_playwright(access_token, date_str)

    async def get_mosreg_schedule_v3(self, access_token, student_id, date_str, retry_auth=True):
        """Резервный метод получения расписания через v3 API"""
        url = f"https://authedu.mosreg.ru/api/family/v3/schedule?student_id={student_id}&date={date_str}"
        headers = self.base_headers.copy()
        headers['Authorization'] = f'Bearer {access_token}'
        headers['auth-token'] = access_token
        headers['Access-Token'] = access_token # New for some subsystems
        
        session = await self._get_session()
        subsystems = ['family', 'familymp', 'educational']
        
        for sub in subsystems:
            headers['X-Mes-Subsystem'] = sub
            try:
                # Активируем подсистему перед запросом
                await self._activate_session(access_token, subsystem=sub)
                
                async with session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        if "application/json" not in resp.headers.get("Content-Type", "").lower():
                            return []
                        data = await resp.json()
                        logger.info(f"Schedule V3 raw response (partial) [{sub}]: {str(data)[:500]}")
                        items = data.get('data', {}).get('items', [])
                        schedule = []
                        for item in items:
                            schedule.append({
                                "subject": item.get('subject_name') or item.get('name', 'Урок'),
                                "time": f"{item.get('start_time', '')} - {item.get('end_time', '')}",
                                "room": item.get('room_name') or '',
                                "has_hw": bool(item.get('homework'))
                            })
                        return schedule
                    elif resp.status == 401:
                        if sub == subsystems[-1]:
                            if retry_auth:
                                await self._activate_session(access_token)
                                return await self.get_mosreg_schedule_v3(access_token, student_id, date_str, retry_auth=False)
                            raise MosregAuthError("Токен истек")
            except MosregAuthError:
                raise
            except Exception as e:
                logger.error(f"Schedule V3 error [{sub}]: {e}")
        return []

    async def get_mosreg_homework(self, access_token, student_id, date_str=None, mesh_id=None):
        """Получает домашние задания через существующую систему расписания (для совместимости с bot.py)"""
        if not date_str:
            from datetime import datetime
            date_str = datetime.now().strftime('%Y-%m-%d')
            
        lessons = await self.get_mosreg_schedule(access_token, student_id, date_str, mesh_id=mesh_id)
        
        hw_results = []
        if lessons:
            for l in lessons:
                if l.get('hw') and l['hw'] not in ['', 'без д/з', 'Нет заданий']:
                    hw_results.append({
                        "subject": l['name'],
                        "description": l['hw'],
                        "link": "" # Мосрег редко отдает прямые ссылки в этом эндпоинте
                    })
        
        return hw_results


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
                    # Сначала проверяем кэш базы данных
                    ans_val = self.db.get_answer_cache(question_text, options_texts)
                    if ans_val:
                        if status_callback: await status_callback(f"♻️ Использую кэш для вопроса {q_num}...")
                    else:
                        if q_num > 1: await asyncio.sleep(40) # Задержка для Videouroki
                        ai_res = await self.ai.get_answer(question_text, options_texts)
                        ans_val = ai_res.get("answer")
                        # Сохраняем в кэш
                        self.db.set_answer_cache(question_text, options_texts, str(ans_val))
                    
                    idx = self._match_index(ans_val, options_texts)
                    
                    # Применяем точность решения
                    acc_mode = user.get('accuracy_mode', 'excellent')
                    import random
                    chance = random.random()
                    if acc_mode == 'modest' and chance > 0.7: # 30% шанс ошибки (~70% точность)
                        wrong_indices = [i for i in range(len(options_elements)) if i != idx]
                        if wrong_indices: idx = random.choice(wrong_indices)
                    elif acc_mode == 'advanced' and chance > 0.8: # 20% шанс ошибки (~80% точность)
                        wrong_indices = [i for i in range(len(options_elements)) if i != idx]
                        if wrong_indices: idx = random.choice(wrong_indices)
                    elif acc_mode == 'excellent' and chance > 0.9: # 10% шанс ошибки (~90% точность)
                        wrong_indices = [i for i in range(len(options_elements)) if i != idx]
                        if wrong_indices: idx = random.choice(wrong_indices)

                    if idx != -1: await options_elements[idx].click()
                    
                    # Имитируем "человеческое" время раздумья
                    delay = user.get('solve_delay', 15)
                    # Если задержка 15 мин на 10-15 вопросов, то это ~1 мин на вопрос
                    await asyncio.sleep(random.uniform(delay * 2, delay * 4)) 

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
        """
        Решает тесты МЭШ / Госуслуги через Playwright.
        """
        async with async_playwright() as p:
            # Запускаем браузер с эмуляцией мобильного устройства для обхода некоторых защит
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            try:
                if status_callback: await status_callback("🌐 Перехожу к тесту МЭШ...")
                await page.goto(test_url, timeout=90000, wait_until="networkidle")
                await asyncio.sleep(5)
                
                # Если перекинуло на Госуслуги — пробуем найти кнопку входа или подождать
                if "gosuslugi.ru" in page.url:
                    if status_callback: await status_callback("🔑 Требуется вход через Госуслуги...")
                    # Здесь в идеале нужно уметь подкидывать куки или ждать, но пока просто заскриншотим
                    if screenshot_callback:
                        path = f"tmp/mesh_auth_{user['user_id']}.png"
                        await page.screenshot(path=path)
                        await screenshot_callback(path)
                    
                    # Пытаемся найти кнопку "Войти" или "Продолжить"
                    login_btn = await page.query_selector("button:has-text('Войти'), .btn-login, button:has-text('Продолжить')")
                    if login_btn:
                        await login_btn.click()
                        await asyncio.sleep(5)

                # Ищем кнопку "Начать тест"
                start_btn = await page.query_selector("button:has-text('Начать'), button:has-text('Приступить'), .start-btn")
                if start_btn:
                    if status_callback: await status_callback("🚀 Начинаю выполнение...")
                    await start_btn.click()
                    await asyncio.sleep(3)
                else:
                    # Если кнопки нет, возможно мы уже в тесте или застряли на логине
                    if status_callback: await status_callback("⚠️ Не вижу кнопку старта. Пробую найти вопросы...")
                
                q_num = 0
                while True:
                    # Проверяем, не закончился ли тест (наличие результатов)
                    final_score = await page.query_selector(".result-score, .final-score, :has-text('Результат')")
                    if final_score:
                        res_text = await final_score.inner_text()
                        return f"✅ Тест завершен! {res_text}"
                    
                    q_num += 1
                    if q_num > 50: break # Страховка
                    
                    # Ищем текст вопроса
                    q_elem = await page.wait_for_selector(".question-text, .q-title, h3, .test-question", timeout=15000)
                    if not q_elem: 
                        if status_callback: await status_callback("🏁 Вопросы закончились или не найдены.")
                        break
                        
                    question_text = await q_elem.inner_text()
                    if status_callback: await status_callback(f"🤔 Вопрос {q_num}: {question_text[:30]}...")
                    
                    # Ищем варианты ответов
                    options_elements = await page.query_selector_all(".answer-item, .option, label, .choice-item")
                    options_texts = []
                    for el in options_elements:
                        txt = await el.inner_text()
                        if txt.strip(): options_texts.append(txt.strip())
                    
                    if not options_elements:
                        if status_callback: await status_callback("ℹ️ Поле свободного ввода или нет вариантов.")
                        # Тут можно добавить логику для ввода текста
                        break

                     # Спрашиваем ИИ (сначала кэш)
                    ans_val = self.db.get_answer_cache(question_text, options_texts)
                    if not ans_val:
                        ai_res = await self.ai.get_answer(question_text, options_texts)
                        ans_val = ai_res.get("answer")
                        self.db.set_answer_cache(question_text, options_texts, str(ans_val))
                    else:
                        if status_callback: await status_callback(f"♻️ Использую кэш для вопроса {q_num}...")
                    
                    idx = self._match_index(ans_val, options_texts)
                    
                    # Применяем точность решения
                    acc_mode = user.get('accuracy_mode', 'excellent')
                    import random
                    chance = random.random()
                    if acc_mode == 'modest' and chance > 0.7: # ~70% точность
                        wrong_indices = [i for i in range(len(options_elements)) if i != idx]
                        if wrong_indices: idx = random.choice(wrong_indices)
                    elif acc_mode == 'advanced' and chance > 0.8: # ~80% точность
                        wrong_indices = [i for i in range(len(options_elements)) if i != idx]
                        if wrong_indices: idx = random.choice(wrong_indices)
                    elif acc_mode == 'excellent' and chance > 0.9: # ~90% точность
                        wrong_indices = [i for i in range(len(options_elements)) if i != idx]
                        if wrong_indices: idx = random.choice(wrong_indices)

                    if idx != -1:
                        await options_elements[idx].click()
                        await asyncio.sleep(1)
                    
                    # Имитируем "человеческое" время раздумья (по дефолту 15 мин на тест)
                    # Если в тесте ~15 вопросов, то это 1 мин на вопрос.
                    delay_min = user.get('solve_delay', 15)
                    # Формула: (delay_min * 60 / 15 questions) * random_factor
                    sleep_time = random.uniform(delay_min * 2, delay_min * 5) 
                    await asyncio.sleep(sleep_time)
                    
                    # Кликаем "Далее" или "Ответить"
                    next_btn = await page.query_selector("button:has-text('Далее'), button:has-text('Ответить'), .next-btn")
                    if next_btn:
                        await next_btn.click()
                        await asyncio.sleep(2)
                    else:
                        await page.keyboard.press("Enter")
                        await asyncio.sleep(2)

                # Итоговый скриншот
                if screenshot_callback:
                    path = f"tmp/mesh_res_{user['user_id']}.png"
                    await page.screenshot(path=path)
                    await screenshot_callback(path)
                
                return "✅ Тест выполнен! Проверьте результат в дневнике."
                
            except Exception as e:
                logger.error(f"MESH solver error: {e}")
                if screenshot_callback:
                    path = f"tmp/mesh_error_{user['user_id']}.png"
                    await page.screenshot(path=path)
                    await screenshot_callback(path)
                return f"❌ Ошибка при решении МЭШ: {str(e)[:100]}"
            finally:
                await browser.close()

    def _match_index(self, ai_val, options):
        if isinstance(ai_val, int):
            return ai_val - 1 if 0 < ai_val <= len(options) else -1
        val_str = str(ai_val).lower().strip()
        for i, opt in enumerate(options):
            if val_str in opt.lower(): return i
        return -1

    async def get_mosreg_schedule_playwright(self, access_token, date_str):
        """Метод получения расписания через браузер с использованием /login/token."""
        from playwright.async_api import async_playwright
        import json
        
        logger.info(f"Starting Auto-Login Playwright fetch for {date_str}")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            intercepted_data = []

            async def handle_response(response):
                if any(x in response.url for x in ["schedule", "diary", "events"]) and response.status == 200:
                    try:
                        text = await response.text()
                        data = json.loads(text)
                        payload = data.get('response') or data.get('data') or data.get('payload') or []
                        if not payload and isinstance(data, list): payload = data
                        if payload: intercepted_data.append(payload)
                    except: pass

            page.on("response", handle_response)
            
            try:
                # Пытаемся зайти через специальный URL авто-логина по токену
                login_url = f"https://myschool.mosreg.ru/login/token?token={access_token}"
                logger.info(f"Navigating to auto-login URL...")
                await page.goto(login_url, wait_until="networkidle", timeout=40000)
                
                # Принудительно ставим identity если редирект на главную случился, но токен не подхватился
                await page.evaluate(f'window.localStorage.setItem("identity", "{access_token}")')
                
                # Переходим на расписание
                schedule_url = f"https://myschool.mosreg.ru/schedule?date={date_str}"
                await page.goto(schedule_url, wait_until="networkidle", timeout=40000)
                
                await asyncio.sleep(5) # Ждем прогрузки всех API ответов

                if intercepted_data:
                    all_items = []
                    events = intercepted_data[0]
                    for ev in events:
                        subject = ev.get('subject_name') or ev.get('title') or ev.get('subject', {}).get('name', 'Урок')
                        start = str(ev.get('start_at') or ev.get('begin_time') or ev.get('start_time') or '')
                        end = str(ev.get('finish_at') or ev.get('end_time') or ev.get('end', '') or '')
                        
                        def parse_t(t):
                            if 'T' in t: return t.split('T')[1][:5]
                            if ' ' in t: return t.split(' ')[1][:5]
                            return t[:5]

                        time_str = f"{parse_t(start)}-{parse_t(end)}"
                        hw = ev.get('homework_text') or ""
                        
                        all_items.append({
                            'name': subject, 'subject': subject,
                            'time': time_str,
                            'hw': hw, 'room': ev.get('room_number', '?')
                        })
                    if all_items: return all_items

                # Если перехват не сработал - пробуем скрапить DOM
                lesson_blocks = await page.query_selector_all("//div[contains(., ':') and string-length(text()) < 10]/ancestor::div[string-length(.) < 1000 and string-length(.) > 50][position()=1]")
                items = []
                for block in lesson_blocks:
                    text = await block.inner_text()
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    if len(lines) >= 2:
                        items.append({'name': lines[0], 'subject': lines[0], 'time': lines[1], 'hw': lines[2] if len(lines) > 2 else "", 'room': ""})
                
                if items: return items
                
                logger.warning(f"Final Playwright attempt failed. Title: {await page.title()}")
                await page.screenshot(path=f"tmp/last_fail_{date_str}.png")

            except Exception as e:
                logger.error(f"Playwright fatal error: {e}")
            finally:
                await browser.close()
        return []
