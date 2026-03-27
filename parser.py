import asyncio
import os
import logging
import re
import base64
import json
import random
import aiohttp
import hashlib
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
        self.last_profile_id = None
        self.active_browsers = {} # {user_id: {'browser': ..., 'context': ..., 'page': ...}}
        if not os.path.exists("sessions"): os.makedirs("sessions")

    async def _get_browser_context(self, p, user_id, headless=True):
        user_data_dir = self.db.get_browser_session(user_id)
        if not user_data_dir:
            user_data_dir = os.path.abspath(os.path.join("sessions", f"user_{user_id}"))
            if not os.path.exists(user_data_dir): os.makedirs(user_data_dir)
            self.db.set_browser_session(user_id, user_data_dir)
        
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=headless,
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        return context
    async def _human_click(self, page, element):
        """Плавное движение мыши к элементу и клик."""
        try:
            box = await element.bounding_box()
            if box:
                x = box['x'] + box['width'] * random.uniform(0.2, 0.8)
                y = box['y'] + box['height'] * random.uniform(0.2, 0.8)
                await page.mouse.move(x, y, steps=random.randint(5, 15))
                await asyncio.sleep(random.uniform(0.1, 0.3))
                await element.click()
            else:
                await element.click()
        except:
            await element.click()

    async def _random_scroll(self, page):
        """Случайный скроллинг для человечности."""
        if random.random() > 0.7:
            direction = random.choice([100, -100, 200, -50])
            await page.mouse.wheel(0, direction)
            await asyncio.sleep(random.uniform(0.5, 1.5))

    def _match_index(self, ai_val, options):
        if isinstance(ai_val, int):
            return ai_val - 1 if 0 < ai_val <= len(options) else -1
        val_str = str(ai_val).lower().strip()
        for i, opt in enumerate(options):
            if val_str in opt.lower(): return i
        return -1


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

    def _find_attachments_recursively(self, obj, seen_links, results):
        """
        Рекурсивно ищет вложения и ссылки. 
        Включает фильтрацию 'мусорных' ссылок (телеметрия, внутренние ID).
        """
        if not obj: return
        
        # Список доменов-исключений (телеметрия, аналитика, внутренние сервисы)
        BLOCKLIST = [
            'telemetry.mos.ru', 'google-analytics.com', 'mc.yandex.ru', 
            'stat.mos.ru', 'monitoring.mos.ru', 'ads.yandex.ru'
        ]

        if isinstance(obj, list):
            for item in obj: self._find_attachments_recursively(item, seen_links, results)
        elif isinstance(obj, dict):
            # 1. Проверка явных полей ссылок
            is_digital = obj.get('is_digital') or obj.get('is_digital_homework') or (obj.get('item_type') == 'digital_task')
            name = obj.get('file_name') or obj.get('name') or obj.get('title') or obj.get('filename') or obj.get('text') or 'Материал'
            
            # Собираем все возможные ключи ссылок
            link = obj.get('link') or obj.get('url') or obj.get('download_url') or obj.get('downloadUrl') or \
                   obj.get('download_link') or obj.get('path') or obj.get('web_link')
            
            # Учебный материал МЭШ (uchebnik.mos.ru)
            if not link and obj.get('material_id'):
                link = f"https://uchebnik.mos.ru/material/view/{obj['material_id']}"
            
            if link and isinstance(link, str) and link.startswith('http'):
                # Нормализация и фильтрация
                if link.startswith('/'): link = f"https://myschool.mosreg.ru{link}"
                
                # Фильтр: Блоклист доменов
                if any(domain in link.lower() for domain in BLOCKLIST): link = None
                
                # Фильтр: Чисто числовые ссылки (часто внутренние ID)
                if link and re.search(r'/\d{7,}/?$', link): link = None

                if link and link not in seen_links:
                    seen_links.add(link)
                    display_name = str(name)
                    if is_digital and 'ЦДЗ' not in display_name.upper():
                        display_name = f"🔥 ЦДЗ: {display_name}"
                    
                    results.append({
                        'title': display_name, 
                        'link': link, 
                        'type': 'digital' if is_digital else 'link',
                        'is_digital': bool(is_digital)
                    })
            
            # 2. Рекурсия по всем полям (поиск вложенных материалов)
            for k, v in obj.items():
                if k in ['materials', 'attachments', 'entries', 'content', 'items']:
                    if isinstance(v, (dict, list)):
                        self._find_attachments_recursively(v, seen_links, results)
                elif isinstance(v, str) and k in ['description', 'text', 'comment', 'value']:
                    # 3. Поиск ссылок в тексте (то, что пишут учителя)
                    found_urls = re.findall(r'https?://[^\s<>"]+', v)
                    for url in found_urls:
                        url = url.rstrip('.,;:')
                        # Фильтрация мусора в тексте
                        if any(domain in url.lower() for domain in BLOCKLIST): continue
                        if re.search(r'/\d{8,}/?$', url): continue
                        
                        if url not in seen_links:
                            seen_links.add(url)
                            # Определяем образовательный домен
                            is_cdz = any(d in url for d in ['resh.edu.ru', 'znaika.space', 'skysmart.ru', 'uchebnik.mos.ru', 'yaklass.ru', 'videouroki.net'])
                            results.append({
                                'title': '🔥 ЦДЗ (из описания)' if is_cdz else 'Ссылка из задания', 
                                'link': url, 
                                'type': 'link',
                                'is_digital': is_cdz
                            })
                elif isinstance(v, (dict, list)) and k not in ['homework', 'homeworks']: # избегаем бесконечной рекурсии если homework ссылается сам на себя
                     self._find_attachments_recursively(v, seen_links, results)

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
                # Сохраняем profile-id если он есть в токене (иногда бывает)
                user_info["profile_id"] = str(decoded.get('profile_id') or decoded.get('profileId') or '')
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
            
        # Если даже ID не нашли, это ошибка
        if not user_info.get("api_ready"): # marker that handshake was done
            user_info["api_ready"] = True

        if user_info.get("profile_id"):
            token_key = hashlib.md5(access_token.encode()).hexdigest()
            if not hasattr(self, '_profile_cache'): self._profile_cache = {}
            self._profile_cache[token_key] = user_info["profile_id"]
            self.last_profile_id = user_info["profile_id"] # legacy fallback
        
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
            "profile_id": str(sid), # Обычно profile_id это и есть id из children
            "mesh_id": str(mesh_id)
        }

    async def get_mosreg_schedule(self, access_token, student_id, date_str, mesh_id=None):
        """Получает расписание через Mosreg API с использованием системы Fallback."""
        cache_key = f"schedule_{student_id}_{date_str}_{mesh_id}"
        # Кеширование временно отключено для отладки
        # cached = self._get_from_cache(cache_key)
        # if cached: return cached
        
        # Если нет profile-id для этого токена, пробуем получить его (рукопожатие)
        token_key = hashlib.md5(access_token.encode()).hexdigest()
        if not hasattr(self, '_profile_cache'): self._profile_cache = {}
        
        if token_key not in self._profile_cache:
            try:
                await self.fetch_mosreg_profile(access_token)
            except Exception as e:
                logger.warning(f"Handshake failed: {e}")
                logger.warning("Could not auto-fetch profile for schedule headers")

        headers = self.base_headers.copy()
        headers['Authorization'] = f'Bearer {access_token}'
        headers['auth-token'] = access_token
        headers['Access-Token'] = access_token
        headers['Referer'] = 'https://myschool.mosreg.ru/'
        
        session = await self._get_session()
        
        # Список эндпоинтов (url, subsystem, id_param, apikey_needed, use_guid)
        endpoints = [
            ("https://authedu.mosreg.ru/api/eventcalendar/v1/api/events", "familyweb", "person_ids", False, True),
            ("https://api.myschool.mosreg.ru/family/mobile/v1/profile/current/schedule", "familymp", "date", False, False),
            ("https://api.myschool.mosreg.ru/family/mobile/v1/schedule/short", "familymp", "student_id", False, False),
            ("https://api.myschool.mosreg.ru/family/v2/diary", "familymp", "student_id", False, False),
            ("https://authedu.mosreg.ru/api/eventcalendar/v1/api/events", "family", "person_ids", True, True),
            ("https://api.myschool.mosreg.ru/family/mobile/v1/schedule", "familymp", "student_id", False, False)
        ]
        
        all_items = []
        for i, (base_url, sub, id_param, needs_apikey, use_guid) in enumerate(endpoints):
            # Для eventcalendar на Mosreg КРИТИЧНО использовать GUID (mesh_id)
            cur_id = mesh_id if ("eventcalendar" in base_url and mesh_id) else (student_id if not use_guid else (mesh_id or student_id))
            if not cur_id and id_param != "date": continue

            try:
                # Формируем URL
                if "schedule/short" in base_url:
                    url = f"{base_url}?{id_param}={cur_id}&from={date_str}&to={date_str}"
                elif "eventcalendar" in base_url:
                    begin_label = "begin_date" if id_param in ["person_ids", "personId"] else "beginDate"
                    end_label = "end_date" if id_param in ["person_ids", "personId"] else "endDate"
                    
                    # Полный список параметров "как в браузере"
                    expand = "homework,marks,absence_reason_id,health_status,nonattendance_reason_id"
                    source_types = "PLAN,AE,EC,EVENTS,AFISHA,ORGANIZER,OLYMPIAD,PROF"
                    
                    url = f"{base_url}?{id_param}={cur_id}&{begin_label}={date_str}&{end_label}={date_str}&expand={expand}&source_types={source_types}"
                elif id_param == "date" and "profile/current" in base_url:
                    url = f"{base_url}?date={date_str}"
                else:
                    url = f"{base_url}?{id_param}={cur_id}&date={date_str}"
                
                h = headers.copy()
                h['X-Mes-Subsystem'] = sub
                h['X-Mes-Role'] = 'student'
                h['profile-type'] = 'student'
                
                # Добавляем profile-id если он есть
                token_key = hashlib.md5(access_token.encode()).hexdigest()
                cached_pid = getattr(self, '_profile_cache', {}).get(token_key)
                if cached_pid:
                    h['profile-id'] = str(cached_pid)
                elif hasattr(self, 'last_profile_id') and self.last_profile_id:
                    h['profile-id'] = str(self.last_profile_id)
                elif mesh_id and mesh_id.isdigit():
                    h['profile-id'] = mesh_id

                if sub == 'familyweb':
                    h['Referer'] = 'https://authedu.mosreg.ru/diary/schedules/day/'

                if needs_apikey:
                    h['apikey'] = '7ef6c62c-7b00-4796-96c6-2c7b00279619'
                
                await self._activate_session(access_token, subsystem=sub)
                
                async with session.get(url, headers=h, timeout=12) as resp:
                    logger.info(f"Schedule fetch [{sub}] {url}: {resp.status}")
                    if resp.status == 200:
                        if "application/json" in resp.headers.get("Content-Type", "").lower():
                            data = await resp.json()
                            raw_payload = data.get('response') or data.get('data') or data.get('payload') or []
                            if not raw_payload and isinstance(data.get('data'), list): raw_payload = data['data']
                            if not raw_payload and isinstance(data, list): raw_payload = data

                            if raw_payload:
                                lessons = self._parse_structural_diary(raw_payload)
                                if lessons:
                                    # Проставляем источник для каждого урока (если нужно боту)
                                    for l in lessons: l['source_sub'] = sub
                                    return lessons
                    elif resp.status == 401 and i == len(endpoints) - 1:
                        raise MosregAuthError("Токен истек")
            except Exception as e:
                logger.error(f"Error in {sub} fetch: {e}")

        # Если прямое API не сработало (например, 403) - используем Playwright
        logger.info("API methods failed or incomplete. Falling back to Playwright interception.")
        return await self.get_mosreg_schedule_playwright(access_token, date_str)

    def _parse_structural_diary(self, raw_payload):
        """Парсит структурированный ответ API (familymp/v2/diary) в список уроков."""
        lessons = []
        for ev in raw_payload:
            if not isinstance(ev, dict): continue
            
            # Базовые данные
            subject = ev.get('subject_name') or ev.get('title') or ev.get('subject', {}).get('name', 'Урок')
            start = ev.get('start_at') or ev.get('begin_time') or ev.get('start_time') or ev.get('start', '')
            end = ev.get('finish_at') or ev.get('end_time') or ev.get('end', '')
            
            def format_t(t):
                if not t: return "??"
                t = str(t)
                if 'T' in t: return t.split('T')[1][:5]
                if ' ' in t: return t.split(' ')[1][:5]
                return t[:5]
            
            time_str = f"{format_t(start)}-{format_t(end)}"
            room = ev.get('room_number') or ev.get('room', {}).get('name', '')
            
            # Извлечение домашнего задания и ЦДЗ (One API Approach)
            hw_text_list = []
            attachments = []
            seen_links = set()
            
            # 1. Текстовое ДЗ из homework (descriptions)
            hw_data = ev.get('homework') or ev.get('homeworks') or {}
            if isinstance(hw_data, dict):
                descs = hw_data.get('descriptions') or hw_data.get('description') or []
                if isinstance(descs, list): hw_text_list.extend([str(d) for d in descs if d])
                elif descs: hw_text_list.append(str(descs))
                self._find_attachments_recursively(hw_data, seen_links, attachments)
            
            # 2. Структурные материалы (Materials/Entries - это и есть ЦДЗ в новом API)
            self._find_attachments_recursively(ev.get('materials', []), seen_links, attachments)
            self._find_attachments_recursively(ev.get('entries', []), seen_links, attachments)
            self._find_attachments_recursively(ev.get('attachments', []), seen_links, attachments)

            hw_final = "; ".join(hw_text_list).strip()
            lessons.append({
                'name': subject,
                'subject': subject,
                'time': time_str,
                'room': room,
                'hw': hw_final,
                'materials': attachments,
                'id': ev.get('id') or ev.get('lesson_id')
            })
        return lessons


    async def get_mosreg_schedule_v3(self, access_token, student_id, date_str, retry_auth=True):
        """Резервный метод получения расписания через v3 API"""
        url = f"https://authedu.mosreg.ru/api/family/v3/schedule?student_id={student_id}&date={date_str}"
        headers = self.base_headers.copy()
        headers['Authorization'] = f'Bearer {access_token}'
        headers['auth-token'] = access_token
        headers['Access-Token'] = access_token # New for some subsystems
        
        session = await self._get_session()
        subsystems = ['familyweb', 'familymp', 'family', 'educational']
        
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
                hw_desc = l.get('hw', '').strip()
                materials = l.get('materials', [])
                
                # Если есть текст ДЗ или материалы
                if (hw_desc and hw_desc not in ['', 'без д/з', 'Нет заданий']) or materials:
                    # Если текста нет, но есть материалы, используем название первого материала как описание
                    if not hw_desc and materials:
                        hw_desc = f"📚 {materials[0]['title']}"
                        if len(materials) > 1:
                            hw_desc += f" (+{len(materials)-1} доп.)"
                    
                    link = ""
                    url_match = re.search(r'https?://\S+', hw_desc)
                    if url_match:
                        link = url_match.group(0).rstrip('.,;:')
                    elif materials:
                        link = materials[0]['link']

                    hw_results.append({
                        "subject": l['name'],
                        "description": hw_desc,
                        "id": l.get('id', hashlib.sha256(f"{l['name']}{l['time']}{date_str}".encode()).hexdigest()),
                        "link": link,
                        "materials": materials
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

    async def solve_test(self, user_id, test_url, accuracy_mode=None, solve_delay_mins=None, status_callback=None, screenshot_callback=None):
        user = self.db.get_user(user_id)
        if not user: return "Ошибка: Профиль не найден.", None
        
        # Переопределяем параметры если они переданы
        if accuracy_mode: user['accuracy_mode'] = accuracy_mode
        if solve_delay_mins: user['solve_delay'] = solve_delay_mins

        if "videouroki.net" in test_url:
            return await self._solve_videouroki(user, test_url, status_callback, screenshot_callback)
        elif "mesh.mos.ru" in test_url or "school.mos.ru" in test_url:
            return await self._solve_mesh(user, test_url, status_callback, screenshot_callback)
        else:
            return "Ошибка: Данная платформа пока не поддерживается.", None

    async def get_test_limit(self, test_url):
        """Пытается определить ограничение по времени на тест."""
        if not any(kw in test_url for kw in ["videouroki.net", "mesh.mos.ru", "school.mos.ru"]):
            return None
            
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={'width': 1280, 'height': 720})
            page = await context.new_page()
            try:
                await page.goto(test_url, timeout=60000, wait_until="domcontentloaded")
                await asyncio.sleep(3)
                content = await page.content()
                
                # Ищем паттерны типа "20 минут", "Время: 30", "на выполнение: 15"
                patterns = [
                    r'([0-9]+)\s*мин',
                    r'Время[:\s]+([0-9]+)',
                    r'ограничение[:\s]+([0-9]+)',
                    r'выполнение[:\s]+([0-9]+)'
                ]
                
                for p in patterns:
                    match = re.search(p, content, re.IGNORECASE)
                    if match:
                        return int(match.group(1))
                
                return None
            except:
                return None
            finally:
                await browser.close()

    async def _solve_videouroki(self, user, test_url, status_callback, screenshot_callback):
        async with async_playwright() as p:
            context = await self._get_browser_context(p, user['user_id'])
            page = context.pages[0] if context.pages else await context.new_page()
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
                    
                    start_btn = await page.query_selector("button.btn.green, input.btn.green, .btn-start")
                    if start_btn:
                        await self._human_click(page, start_btn)
                    
                    await asyncio.sleep(3)
                
                q_num = 0
                total_q = 10 
                
                while True:
                    progress = min(1.0, q_num / total_q)
                    bar = "█" * int(progress * 10) + "░" * (10 - int(progress * 10))
                    p_text = f"📊 Прогресс: [{bar}] {int(progress*100)}%\n"
                    
                    if await page.query_selector(".test-results, .final-score"): break
                    
                    q_num += 1
                    if q_num > 50: break
                    
                    question_elem = await page.wait_for_selector("h3, .v-question-text, .quest-text", timeout=10000)
                    if not question_elem: break
                    
                    question_text = await question_elem.inner_text()
                    options_elements = await page.query_selector_all(".v-option, .answer-item, .quest-ans-item")
                    options_texts = [await opt.inner_text() for opt in options_elements]
                    
                    if status_callback: await status_callback(f"{p_text}🤔 Решаю вопрос {q_num}: {question_text[:50]}...")
                    
                    # Зрение: если вариантов нет или текст короткий, делаем скриншот
                    image_b64 = None
                    if not options_texts or len(question_text) < 5:
                        screenshot_bytes = await page.screenshot()
                        image_b64 = base64.b64encode(screenshot_bytes).decode()
                    
                    ans_data = await self.ai.get_answer(question_text, options_texts, image_b64)
                    ans_val = ans_data.get('answer')
                    idx = self._match_index(ans_val, options_texts)
                    
                    # Применяем точность решения
                    acc_mode = user.get('accuracy_mode', 'perfect')
                    chance = random.random()
                    if acc_mode == 'basic' and chance > 0.7:
                        wrong_indices = [i for i in range(len(options_elements)) if i != idx]
                        if wrong_indices: idx = random.choice(wrong_indices)
                    elif acc_mode == 'advanced' and chance > 0.85:
                        wrong_indices = [i for i in range(len(options_elements)) if i != idx]
                        if wrong_indices: idx = random.choice(wrong_indices)
                    elif acc_mode == 'perfect' and chance > 0.95:
                        wrong_indices = [i for i in range(len(options_elements)) if i != idx]
                        if wrong_indices: idx = random.choice(wrong_indices)

                    if idx != -1:
                        await self._human_click(page, options_elements[idx])
                        await asyncio.sleep(1)
                    
                    await self._random_scroll(page)
                    
                    sleep_time = random.uniform(5.0, 15.0) 
                    if status_callback: await status_callback(f"{p_text}⏳ Обдумываю... ({int(sleep_time)} сек)")
                    await asyncio.sleep(sleep_time)

                    next_btn = await page.query_selector("button:has-text('Далее'), .btn-next")
                    if next_btn:
                        await self._human_click(page, next_btn)
                    else:
                        await page.keyboard.press("Enter")
                    await asyncio.sleep(2)
                
                # Итоговый скриншот перед выходом
                if not os.path.exists("tmp"): os.makedirs("tmp")
                screenshot_path = f"tmp/res_{user['user_id']}_{int(datetime.now().timestamp())}.png"
                await page.screenshot(path=screenshot_path)
                
                result_text = await page.inner_text(".test-results, .final-score")
                self.db.add_test_score(user['user_id'], test_url, result_text)
                self.db.add_test_history(user['user_id'], test_url, result_text)
                return f"✅ Готово! Результат: {result_text}", screenshot_path
            except Exception as e:
                logger.error(f"Videouroki solver error: {e}")
                return f"❌ Ошибка: {e}", None
            finally:
                if user.get('user_id') not in self.active_browsers:
                    try: await context.close()
                    except: pass


    async def init_qr_login(self, user_id):
        """Инициализирует вход через QR-код с использованием персистентной сессии."""
        if not os.path.exists("tmp"): os.makedirs("tmp")
        
        # Если старый браузер еще висит - закрываем
        if user_id in self.active_browsers:
            try: await self.active_browsers[user_id]['context'].close()
            except: pass
            
        p = await async_playwright().start()
        context = await self._get_browser_context(p, user_id, headless=True)
        page = context.pages[0] if context.pages else await context.new_page()
        
        try:
            # Переход на страницу логина
            await page.goto("https://myschool.mosreg.ru/login", wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            
            qr_btn = await page.query_selector("button:has-text('QR'), .qr-login-btn, [data-test-id='qr-login']")
            if qr_btn:
                await qr_btn.click()
                await asyncio.sleep(2)
            
            qr_selector = "img[alt*='QR'], .qr-code, canvas, [data-test-id='qr-code']"
            qr_elem = await page.wait_for_selector(qr_selector, timeout=15000)
            
            path = f"tmp/qr_{user_id}.png"
            if qr_elem: await qr_elem.screenshot(path=path)
            else: await page.screenshot(path=path)
                
            self.active_browsers[user_id] = {
                'playwright': p,
                'context': context,
                'page': page,
                'started_at': datetime.now()
            }
            return path
        except Exception as e:
            logger.error(f"QR Init error: {e}")
            try: 
                if context: await context.close()
            except: pass
            await p.stop()
            return None

    async def check_qr_login_status(self, user_id):
        """Проверяет, произошел ли вход после сканирования QR."""
        if user_id not in self.active_browsers:
            return "expired", None
            
        session = self.active_browsers[user_id]
        page = session['page']
        
        try:
            # Проверяем URL и наличие элементов дашборда
            current_url = page.url
            if "login" not in current_url and any(x in current_url for x in ["diary", "schedule", "profile", "main"]):
                # Вход выполнен!
                # Пытаемся вытянуть токен из localStorage или cookies
                token = await page.evaluate('window.localStorage.getItem("identity") || window.localStorage.getItem("auth-token")')
                if not token:
                    cookies = await session['context'].cookies()
                    # Можем поискать специфическую печеньку
                
                # Получаем профиль для подтверждения
                # profile_data = ...
                return "success", token
                
            # Проверка на таймаут (5 минут)
            if datetime.now() - session['started_at'] > timedelta(minutes=5):
                await self.close_qr_session(user_id)
                return "timeout", None
                
            return "waiting", None
        except Exception as e:
            logger.error(f"QR check error: {e}")
            return "error", None

    async def close_qr_session(self, user_id):
        if user_id in self.active_browsers:
            s = self.active_browsers[user_id]
            try:
                await s['browser'].close()
                await s['playwright'].stop()
            except: pass
            del self.active_browsers[user_id]

    async def attach_screenshot_to_homework(self, user_id, hw_id, date_str, screenshot_path):
        """Прикрепляет скриншот к домашнему заданию на портале."""
        user = self.db.get_user(user_id)
        if not user: return False, "Профиль не найден"
        
        # Если есть активный браузер — используем его, иначе создаем новый (через токен)
        if user_id in self.active_browsers:
            page = self.active_browsers[user_id]['page']
        else:
            # Создаем временную сессию по токену
            p = await async_playwright().start()
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            
            # Логин по токену
            login_url = f"https://myschool.mosreg.ru/login/token?token={user['token_mos']}"
            await page.goto(login_url, wait_until="networkidle")
            # Сохраняем для закрытия позже
            self.active_browsers[user_id] = {'playwright': p, 'browser': browser, 'context': context, 'page': page}

        try:
            # Переход в дневник на нужную дату для поиска ссылки на задание
            diary_url = f"https://myschool.mosreg.ru/diary/schedules/day/{date_str}"
            await page.goto(diary_url, wait_until="networkidle")
            await asyncio.sleep(3)
            
            # Пытаемся найти ссылку на задание по ID или названию
            # Обычно это переход в карточку урока/задания
            # В Mosreg/MESH часто ссылка на ДЗ сопряжена с lesson_id или hw_id
            hw_link_selector = f"a[href*='{hw_id}'], a[href*='homework'], .homework-item"
            hw_link = await page.query_selector(hw_link_selector)
            
            if hw_link:
                await hw_link.click()
                await asyncio.sleep(3)
            else:
                # Если не нашли прямую ссылку, пробуем через API подсистему или поиск по тексту
                # (Пропустим сложный поиск для прототипа, предположим мы уже на нужной странице 
                # или можем сконструировать URL если формат известен)
                # Formats: https://myschool.mosreg.ru/learning/homeworks/{hw_id}
                card_url = f"https://myschool.mosreg.ru/learning/homeworks/{hw_id}"
                await page.goto(card_url, wait_until="networkidle")
                await asyncio.sleep(2)

            # Ищем кнопку "Загрузить файл" или "Прикрепить"
            # В MESH/Mosreg: "Добавить файл", ".add-file-btn", "[type='file']"
            file_input = await page.query_selector("input[type='file'], .file-upload-input")
            if not file_input:
                # Если кнопка скрыта, кликаем на "Добавить"
                add_btn = await page.query_selector("button:has-text('Добавить'), button:has-text('Прикрепить'), .add-hw-file")
                if add_btn: 
                    await add_btn.click()
                    await asyncio.sleep(1)
                    file_input = await page.query_selector("input[type='file']")

            if file_input:
                await file_input.set_input_files(screenshot_path)
                await asyncio.sleep(3)
                
                # Ищем кнопку "Сохранить" или "Отправить на проверку"
                save_btn = await page.query_selector("button:has-text('Сохранить'), button:has-text('Отправить'), .submit-btn")
                if save_btn:
                    await save_btn.click()
                    await asyncio.sleep(2)
                    return True, "Скриншот успешно прикреплен!"
                else:
                    return True, "Файл загружен, но кнопка подтверждения не найдена (проверьте вручную)."
            else:
                return False, "Не удалось найти поле для загрузки файла на портале."
                
        except Exception as e:
            logger.error(f"Attach error: {e}")
            return False, f"Ошибка при прикреплении: {str(e)[:50]}"
        finally:
            # Не закрываем если это активная сессия решения, но закрываем если временная
            if 'started_at' not in self.active_browsers.get(user_id, {}):
                await self.close_qr_session(user_id)

    async def _solve_mesh(self, user, test_url, status_callback, screenshot_callback):
        """
        Решает тесты МЭШ / Госуслуги через Playwright с использованием персистентной сессии.
        Теперь включает 'Тихий Режим' (извлечение ответов из кода).
        """
        async with async_playwright() as p:
            context = await self._get_browser_context(p, user['user_id'])
            page = context.pages[0] if context.pages else await context.new_page()
            
            # Хранилище ответов для этой сессии
            intercepted_answers = {} # {question_text: correct_option_text}
            
            async def handle_response(response):
                try:
                    url = response.url
                    # Ищем эндпоинты с данными теста (обычно /start или расширенный JSON)
                    if "application/json" in (response.headers.get("content-type") or "") and \
                       any(x in url for x in ["testplayer/challenge", "test_data", "exam/api"]):
                        
                        text = await response.text()
                        data = json.loads(text)
                        
                        # Парсим структуру MESH Challenge
                        tasks = data.get('tasks') or data.get('data', {}).get('tasks') or []
                        if not tasks and 'questions' in data: tasks = data['questions']
                        
                        for task in tasks:
                            q_text = task.get('question_text') or task.get('text') or ""
                            # Убираем HTML теги из вопроса
                            q_text = re.sub(r'<[^>]+>', '', q_text).strip()
                            
                            options = task.get('options') or task.get('answers') or []
                            for opt in options:
                                if opt.get('is_correct') or opt.get('correct'):
                                    ans_text = opt.get('text') or opt.get('answer_text') or ""
                                    ans_text = re.sub(r'<[^>]+>', '', ans_text).strip()
                                    if q_text and ans_text:
                                        intercepted_answers[q_text[:200]] = ans_text
                                        logger.info(f"SilentSolver: Captured answer for '{q_text[:30]}...' -> '{ans_text[:30]}...'")
                except Exception as e:
                    pass

            page.on("response", handle_response)
            
            try:
                if status_callback: await status_callback("🌐 Перехожу к тесту МЭШ...")
                await page.goto(test_url, timeout=90000, wait_until="networkidle")
                await asyncio.sleep(5)
                
                # Проверка на логин
                current_url = page.url
                if "login" in current_url or "auth" in current_url or await page.query_selector("form#login-form, .login-form, button:has-text('Войти')"):
                    return "NEEDS_QR", None

                start_btn = await page.query_selector("button:has-text('Начать'), button:has-text('Приступить'), button:has-text('Пройти'), .start-btn")
                if start_btn:
                    if status_callback: await status_callback("🚀 Начинаю выполнение...")
                    await self._human_click(page, start_btn)
                    await asyncio.sleep(3)
                
                q_num = 0
                total_q = 15 
                
                while True:
                    progress = min(1.0, q_num / max(1, total_q))
                    bar = "█" * int(progress * 10) + "░" * (10 - int(progress * 10))
                    p_text = f"📊 Прогресс: [{bar}] {int(progress*100)}%\n"
                    
                    final_score = await page.query_selector(".result-score, .final-score, :has-text('Результат'), :has-text('Баллы')")
                    if final_score:
                        res_text = await final_score.inner_text()
                        self.db.add_test_score(user['user_id'], test_url, res_text)
                        self.db.add_test_history(user['user_id'], test_url, res_text + " (МЭШ)")
                        screenshot_path = f"tmp/mesh_res_{user['user_id']}_{int(datetime.now().timestamp())}.png"
                        await page.screenshot(path=screenshot_path)
                        return f"✅ Тест завершен! {res_text}", screenshot_path
                    
                    q_num += 1
                    if q_num > 60: break
                    
                    q_elem = await page.wait_for_selector(".question-text, .q-title, h3, .test-question, .task-text", timeout=15000)
                    if not q_elem: break
                        
                    question_text_raw = await q_elem.inner_text()
                    question_text_clean = re.sub(r'<[^>]+>', '', question_text_raw).strip()
                    
                    if status_callback: await status_callback(f"{p_text}🤔 Вопрос {q_num}: {question_text_clean[:40]}...")
                    
                    options_elements = await page.query_selector_all(".answer-item, .option, label, .choice-item, .task-option")
                    options_texts = [re.sub(r'<[^>]+>', '', await el.inner_text()).strip() for el in options_elements]
                    
                    idx = -1
                    # --- ПЫТАЕМСЯ НАЙТИ ОТВЕТ В ПЕРЕХВАЧЕННОМ JSON (Silent Mode) ---
                    found_silent = False
                    if question_text_clean[:200] in intercepted_answers:
                        correct_text = intercepted_answers[question_text_clean[:200]]
                        idx = self._match_index(correct_text, options_texts)
                        if idx != -1:
                            found_silent = True
                            if status_callback: await status_callback(f"{p_text}⚡️ Нашел ответ в коде! (точность 100%)")
                    
                    # --- ЕСЛИ НЕ НАШЛИ - ИСПОЛЬЗУЕМ ИИ ---
                    if idx == -1:
                        ans_data = await self.ai.get_answer(question_text_raw, options_texts)
                        ans_val = ans_data.get('answer')
                        idx = self._match_index(ans_val, options_texts)
                        
                        # Точность (только для ИИ ответов)
                        acc_mode = user.get('accuracy_mode', 'perfect')
                        if acc_mode != 'perfect' and random.random() > 0.8:
                             wrong_indices = [i for i in range(len(options_elements)) if i != idx]
                             if wrong_indices: idx = random.choice(wrong_indices)

                    if idx != -1:
                        await self._human_click(page, options_elements[idx])
                        await asyncio.sleep(1)
                    
                    # Задержка
                    delay_min = int(user.get('solve_delay', 15))
                    # Для беззвучного режима можно чуть быстрее, но не слишком палевно
                    sleep_time = random.uniform(5.0, 15.0) if found_silent else random.uniform(10.0, 30.0)
                    if status_callback: await status_callback(f"⏳ Думаю... ({int(sleep_time)} сек)")
                    await asyncio.sleep(sleep_time)
                    
                    next_btn = await page.query_selector("button:has-text('Далее'), button:has-text('Ответить'), .next-btn, .submit-btn")
                    if next_btn:
                        await self._human_click(page, next_btn)
                    else:
                        await page.keyboard.press("Enter")
                    await asyncio.sleep(2)

                screenshot_path = f"tmp/mesh_res_{user['user_id']}.png"
                await page.screenshot(path=screenshot_path)
                return f"✅ Тест выполнен!", screenshot_path
            except Exception as e:
                logger.error(f"MESH solver error: {e}")
                return f"❌ Ошибка МЭШ: {e}", None
            finally:
                if user['user_id'] not in self.active_browsers:
                    try: await context.close()
                    except: pass


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
                    # Используем единый структурный парсер для перехваченных данных
                    # Берем самый длинный (полный) ответ
                    intercepted_data.sort(key=len, reverse=True)
                    events = intercepted_data[0]
                    lessons = self._parse_structural_diary(events)
                    if lessons: return lessons

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
