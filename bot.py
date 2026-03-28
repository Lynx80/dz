import asyncio
import html
from typing import Optional
import logging
import os
import re
import hashlib
from datetime import datetime, timedelta
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, ReplyKeyboardRemove
from aiogram.exceptions import TelegramBadRequest
from aiogram.client.session.aiohttp import AiohttpSession

from database import Database
from parser import ParserService, MosregAuthError

load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и БД
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8684063011:AAHpBjpulnliaz2-Qnnvh_DPUwQaNygj8lg")
PROXY_URL = os.getenv("TELEGRAM_PROXY")

if PROXY_URL:
    logger.info(f"Using proxy: {PROXY_URL}")
    session = AiohttpSession(proxy=PROXY_URL)
    bot = Bot(token=API_TOKEN, session=session)
else:
    bot = Bot(token=API_TOKEN)

dp = Dispatcher(storage=MemoryStorage())
db = Database()
parser = ParserService()

# ─── СОСТОЯНИЯ (FSM) ───
class BotStates(StatesGroup):
    MAIN_MENU = State()
    WEEK_SELECTION = State()
    DAY_SELECTION = State()
    HOMEWORK_VIEW = State()
    AUTO_SOLVE_WEEK = State()
    AUTO_SOLVE_DAY = State()
    SETTINGS = State()
    PROFILE = State()
    WAITING_FOR_TOKEN = State()
    WAITING_FOR_QR_SCAN = State()

# ─── КЛАВИАТУРЫ ───

def get_main_menu_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📚 МОЁ ДЗ")
    builder.button(text="👤 ПРОФИЛЬ")
    builder.button(text="⚙️ НАСТРОЙКИ")
    
    # Динамический текст кнопки ДЗ (Синхронизировано с обработчиком)
    now = datetime.now()
    weekday = now.weekday()
    hour = now.hour
    
    if weekday == 4: # Пятница
        hw_text = "📚 ДЗ НА СЕГОДНЯ" if hour < 15 else "📚 ДЗ НА ПОНЕДЕЛЬНИК"
    elif weekday == 5 or weekday == 6: # Суббота или Воскресенье
        hw_text = "📚 ДЗ НА ПОНЕДЕЛЬНИК"
    else: # Пн-Чт
        hw_text = "📚 ДЗ НА СЕГОДНЯ" if hour < 15 else "📚 ДЗ НА ЗАВТРА"
        
    builder.button(text=hw_text)
    builder.adjust(1, 2, 1)
    return builder.as_markup(resize_keyboard=True)

def get_week_kb(prefix="week"):
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 ПРЕДЫДУЩАЯ", callback_data=f"{prefix}_prev")
    builder.button(text="📅 ТЕКУЩАЯ", callback_data=f"{prefix}_curr")
    builder.button(text="📅 СЛЕДУЮЩАЯ", callback_data=f"{prefix}_next")
    builder.adjust(2, 1)
    return builder.as_markup()

def get_days_kb(week_offset=0, prefix="manual"):
    builder = InlineKeyboardBuilder()
    today = datetime.now()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    days_ru = ["ПН", "ВТ", "СР", "ЧТ", "ПТ"]
    for i in range(5):
        d = monday + timedelta(days=i)
        date_str = d.strftime('%Y-%m-%d')
        builder.button(text=f"{days_ru[i]} {d.strftime('%d.%m')}", callback_data=f"{prefix}_{date_str}")
    builder.adjust(3, 2)
    return builder.as_markup()

def get_hw_reply_kb():
    builder = ReplyKeyboardBuilder()
    # Кнопки ИИ (отдельный ряд)
    builder.row(types.KeyboardButton(text="🧠 РЕШИТЬ ВСЁ [ЦДЗ]"), types.KeyboardButton(text="🔍 ВЫБОРОЧНО [ЦДЗ]"))
    # Кнопки управления (внизу)
    builder.row(types.KeyboardButton(text="🔄 ОБНОВИТЬ"), types.KeyboardButton(text="🔙 НАЗАД"), types.KeyboardButton(text="🏠 МЕНЮ"))
    return builder.as_markup(resize_keyboard=True)

def get_nav_reply_kb():
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🔙 НАЗАД"), types.KeyboardButton(text="🏠 МЕНЮ"))
    return builder.as_markup(resize_keyboard=True)

def get_hw_toggles_kb(hw_list, date_str):
    """Инлайн-клавиатура для управления статусом И решения конкретных тестов"""
    builder = InlineKeyboardBuilder()
    
    # 1. Кнопки предметов (для отметки выполнения)
    for hw in hw_list:
        status_icon = "✅" if hw['is_done'] else ("🌟" if hw.get('is_ec') else "❌")
        subj_name = hw['subject']
        if len(subj_name) > 12: subj_name = subj_name[:10] + ".."
        builder.button(text=f"{status_icon} {subj_name}", callback_data=f"hw_done:{date_str}:{hw['hash']}")
    
    builder.adjust(2)
    
    # 2. Кнопки быстрого решения для КАЖДОГО теста отдельно
    for hw in hw_list:
        if not hw['is_done'] and not hw.get('is_ec'):
            desc = hw.get('description', '').lower()
            if any(x in desc for x in ['http', 'тест', 'цдз', 'мэш']):
                 builder.row(types.InlineKeyboardButton(
                     text=f"🧠 РЕШИТЬ: {hw['subject'][:15]}", 
                     callback_data=f"ai_select_subj:{hw['id']}:{date_str}"
                 ))
    
    # 3. Главные кнопки ИИ в самом низу
    builder.row(
        types.InlineKeyboardButton(text="🧠 РЕШИТЬ ВСЁ", callback_data=f"ai_solve_all:{date_str}"),
        types.InlineKeyboardButton(text="🔍 ВЫБОРОЧНО", callback_data=f"ai_solve_select:{date_str}")
    )
    
    # Кнопка ОБНОВИТЬ
    builder.row(types.InlineKeyboardButton(text="🔄 ОБНОВИТЬ СПИСОК", callback_data=f"refresh_hw_list:{date_str}"))
    
    return builder.as_markup()

def get_solve_accuracy_kb(task_id, date_str, is_batch=False):
    """Клавиатура выбора точности решения (Шаг 2)"""
    builder = InlineKeyboardBuilder()
    prefix = "batch_acc" if is_batch else f"task_acc:{task_id}"
    
    # Режим имитации теперь описывается тут (по желанию пользователя)
    desc = "🤖 **Имитация человека:** бот сам меняет время ответа на каждый вопрос, чтобы поведение выглядело естественно."
    
    builder.button(text="⭐ Базовая (70%)", callback_data=f"{prefix}:basic:{date_str}")
    builder.button(text="⭐⭐ Продвинутая (85%)", callback_data=f"{prefix}:advanced:{date_str}")
    builder.button(text="⭐⭐⭐ Идеальная (95%)", callback_data=f"{prefix}:perfect:{date_str}")
    
    back_data = "ai_solve_select" if is_batch else f"back_to_select_subj:{date_str}"
    builder.button(text="🔙 Назад", callback_data=back_data)
    
    builder.adjust(1)
    return builder.as_markup()

def get_solve_time_kb(task_id, accuracy, date_str):
    """Клавиатура выбора времени (Шаг 3)"""
    builder = InlineKeyboardBuilder()
    options = [5, 10, 15, 25]
    for mins in options:
        # Теперь ведет к выбору режима
        builder.button(text=f"⏱️ {mins} мин", callback_data=f"sel_mode:{task_id}:{accuracy}:{mins}:{date_str}")
        
    is_batch = task_id == "all"
    back_data = f"ai_solve_all:{date_str}" if is_batch else f"ai_select_subj:{task_id}:{date_str}"
    builder.button(text="🔙 Назад", callback_data=back_data)
    builder.adjust(2)
    return builder.as_markup()

def get_solve_final_mode_kb(task_id, accuracy, mins, date_str):
    """Клавиатура выбора режима (Шаг 4)"""
    builder = InlineKeyboardBuilder()
    # Кнопки старта
    builder.button(text="🤖 С имитацией человека", callback_data=f"start_solve:{task_id}:{accuracy}:human:{mins}:{date_str}")
    builder.button(text="⏱️ Обычный режим", callback_data=f"start_solve:{task_id}:{accuracy}:normal:{mins}:{date_str}")
    
    builder.button(text="🔙 Назад", callback_data=f"select_time:{task_id}:{accuracy}:{date_str}")
    builder.adjust(1)
    return builder.as_markup()

def get_batch_solve_pre_kb(date_str):
    builder = InlineKeyboardBuilder()
    builder.button(text="🎯 ТОЧНО (90+%)", callback_data=f"batch_solve_{date_str}_excellent")
    builder.button(text="⚡ БЫСТРО (70+%)", callback_data=f"batch_solve_{date_str}_modest")
    builder.button(text="🔙 НАЗАД", callback_data=f"refresh_day_{date_str}_manual")
    builder.adjust(2, 1)
    return builder.as_markup()

def get_settings_kb(solve_delay=15, accuracy_mode="advanced"):
    builder = InlineKeyboardBuilder()
    acc_text = {"modest": "70+%", "advanced": "80+%", "excellent": "90+%"}.get(accuracy_mode, "80+%")
    builder.button(text=f"⏱ ВРЕМЯ РЕШЕНИЯ: {solve_delay} МИН", callback_data="set_speed_menu")
    builder.button(text=f"🎯 ТОЧНОСТЬ: {acc_text}", callback_data="set_accuracy_menu")
    builder.button(text="🔄 ОБНОВИТЬ ДАННЫЕ", callback_data="refresh_data")
    builder.button(text="💳 ПОДПИСКА", callback_data="subscription_info")
    builder.button(text="🔙 ВЕРНУТЬСЯ В ГЛАВНОЕ МЕНЮ", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_profile_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 ОБНОВИТЬ ПРОФИЛЬ", callback_data="refresh_profile_data")
    builder.button(text="🗑 УДАЛИТЬ ТОКЕН", callback_data="delete_token_confirm")
    builder.button(text="🔙 НАЗАД", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_speed_kb(current_speed=15):
    builder = InlineKeyboardBuilder()
    for s in [1, 5, 10, 15, 20, 25]:
        text = f"✅ {s} МИН" if s == current_speed else f"{s} МИН"
        if s == 15: text += " (ПО УМОЛЧАНИЮ)"
        builder.button(text=text, callback_data=f"save_speed_{s}")
    builder.button(text="🔙 НАЗАД", callback_data="back_to_settings")
    builder.adjust(1)
    return builder.as_markup()

def get_accuracy_kb(current_acc="advanced"):
    builder = InlineKeyboardBuilder()
    modes = [("modest", "🥉 БАЗОВЫЙ (70+%)"), ("advanced", "🥈 СТАНДАРТ (80+%)"), ("excellent", "🥇 МАКСИМУМ (90+%)")]
    for m_id, m_text in modes:
        text = f"✅ {m_text}" if m_id == current_acc else m_text
        if m_id == "advanced": text += " (ПО УМОЛЧАНИЮ)"
        builder.button(text=text, callback_data=f"save_acc_{m_id}")
    builder.button(text="🔙 НАЗАД", callback_data="back_to_settings")
    builder.adjust(1)
    return builder.as_markup()

def get_token_help_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="ЧТО ТАКОЕ ТОКЕН ❓", callback_data="what_is_token")
    builder.button(text="🔙 ВЕРНУТЬСЯ В ГЛАВНОЕ МЕНЮ", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

# ─── ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ───

def classify_hw(desc: str, url: str) -> tuple[str, str]:
    """Возвращает (тип, иконка)"""
    desc_l = desc.lower().strip()
    url_l = url.lower()
    
    # 0. ИГНОРИРУЕМ "БЕЗ ДЗ"
    if any(x in desc_l for x in ["без дз", "без д/з", "нет заданий", "не задано", "нет дз", "без домашнего задания"]) or not desc_l:
        return "нет", "🕊️"

    # 1. ТЕСТ (Приоритет ссылкам)
    if any(x in url_l for x in ["/test", "/exam", "/quiz", "/assessment", "/training", "videouroki.net/tests", "uchebnik.mos.ru/exam", "gosuslugi.ru/edu-content", "edu-content"]):
        return "тест", "⚡"
    
    # 2. ПИСЬМЕННОЕ (Приоритет действию)
    # Если есть номера, страницы или слова действия типа "выучить", "доделать"
    written_kws = ["номер", "стр.", "стр ", "с.", "упр", "упражнен", "задач", "параграф", "№", "выучить", "доделать", "сделать", "решить", "выполнить", "написать"]
    if any(x in desc_l for x in written_kws):
        return "письм.", "✍️"

    # 3. ТЕСТ (По ключевым словам в тексте)
    if any(x in desc_l for x in ["тест", "тренажер", "контрольн", "экзамен", "цдз", "📚"]):
        return "тест", "⚡"
    
    # 4. ВИДЕО
    if any(x in desc_l for x in ["видео", "посмотреть", "ролик", "видеоурок"]) or \
       any(x in url_l for x in ["youtube.com", "youtu.be", "rutube.ru", "vimeo.com", "/video/"]):
        return "видео", "📺"
        
    # 5. ТЕОРИЯ / МАТЕРИАЛ (Если не попало в письменное выше)
    if any(x in desc_l for x in ["прочитать", "повторить", "лекци", "материал", "правил", "изучить"]) or \
       any(x in url_l for x in ["/material", "/lesson", "/library", "resh.edu.ru"]):
        return "теория", "📖"
        
    # 6. ПО УМОЛЧАНИЮ
    return "письм.", "✍️"

async def check_token(message: types.Message, user):
    if not user or not user.get('token_mos'):
        help_text = (
            "P.S. Без токена — никаких тестов. Так что действуй! 🔥\n"
            "Для МО обязательно сначала войти в аккаунт, а потом получить токен!"
        )
        if isinstance(message, types.CallbackQuery):
            await message.message.answer(help_text, reply_markup=get_token_help_kb(), disable_web_page_preview=True, parse_mode="Markdown")
        else:
            await message.answer(help_text, reply_markup=get_token_help_kb(), disable_web_page_preview=True, parse_mode="Markdown")
        return False
    return True

async def show_day_homework(message: types.Message, user: dict, date_str: str, state: FSMContext, is_callback: bool = False):
    """Общий метод для отображения расписания и ДЗ на конкретный день."""
    # 1. Получаем данные
    try:
        # Автоматическое восстановление ID если они потеряны (для старых записей в БД)
        if not user.get('student_id') or not user.get('mesh_id'):
            logger.info(f"User {user['user_id']} missing IDs. Repairing...")
            new_p = await parser.fetch_mosreg_profile(user['token_mos'])
            if new_p:
                db.update_user(user['user_id'], 
                             student_id=new_p.get('student_id'), 
                             mesh_id=new_p.get('mesh_id'),
                             first_name=new_p.get('first_name'),
                             last_name=new_p.get('last_name'),
                             grade=new_p.get('grade'))
                user.update(new_p)
                logger.info(f"User {user['user_id']} IDs repaired: Student={user['student_id']}, Mesh={user['mesh_id']}")

        schedule = await parser.get_mosreg_schedule(user['token_mos'], user['student_id'], date_str, mesh_id=user.get('mesh_id'))
        homeworks = await parser.get_mosreg_homework(user['token_mos'], user['student_id'], date_str, mesh_id=user.get('mesh_id'))
    except MosregAuthError:
        text = (
            "⚠️ ВАША СЕССИЯ ИСТЕКЛА!\n\nТОКЕН БОЛЬШЕ НЕ ДЕЙСТВИТЕЛЕН. ПОЖАЛУЙСТА, ОБНОВИТЕ ЕГО:\n"
            "🔗 [ПОЛУЧИТЬ НОВЫЙ ТОКЕН](https://authedu.mosreg.ru/v2/token/refresh)\n\n"
            "ПРОСТО ОТПРАВЬТЕ НОВЫЙ ТОКЕН МНЕ."
        )
        kb = InlineKeyboardBuilder().button(text="🔙 В МЕНЮ", callback_data="back_to_main").as_markup()
        if is_callback:
            await message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        else:
            await message.answer(text, reply_markup=kb, parse_mode="Markdown")
        return

    # Подготовка даты для заголовка
    days_ru = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    target_date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    day_name = days_ru[target_date_obj.weekday()]
    
    # ─── Анализ и классификация ───
    unique_tasks = {} # {(subject, desc): first_lesson_num}
    stats = {"тест": 0, "видео": 0, "теория": 0, "письм.": 0}
    
    # ─── Сбор всех уникальных заданий для статистики и кнопок ───
    all_unique_tasks = []
    task_keys = set()
    for item in (schedule or []):
        hw_item = next((h for h in homeworks if h['subject'].lower() in item['subject'].lower() or item['subject'].lower() in h['subject'].lower()), None)
        if hw_item:
            desc = hw_item['description'].strip()
            task_key = (item['subject'].lower().strip(), desc) # Use strip for subject in key
            if task_key not in task_keys:
                task_keys.add(task_key)
                url_match = re.search(r'https?://\S+', desc)
                url = url_match.group(0) if url_match else ""
                hw_type, _ = classify_hw(desc, url)
                if hw_type != "нет":
                    # СТРОГИЙ ХЕШ (с strip)
                    hw_hash = hashlib.md5(f"{item['subject'].strip()}:{desc}".encode()).hexdigest()
                    is_done = db.is_hw_completed(user['user_id'], date_str, hw_hash)
                    
                    # Внеурочка не идет в обязательную статистику, если нет ДЗ
                    is_ec = item.get('source') == 'EC'
                    
                    all_unique_tasks.append({
                        'subject': item['subject'],
                        'desc': desc,
                        'type': hw_type,
                        'hash': hw_hash,
                        'is_done': is_done,
                        'task_key': task_key,
                        'is_ec': is_ec
                    })
                    if not is_ec:
                        stats[hw_type] += 1

    # ─── ОСНОВНОЙ ВЫВОД РАСПИСАНИЯ ───
    day_name = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"][target_date_obj.weekday()]
    text_parts = [f"<b>🗓 Расписание на {target_date_obj.strftime('%d.%m')} ({day_name})</b>\n"]
    
    unique_tasks_shown = {} # {(subject, clean_desc): lesson_num}
    
    for i, item in enumerate(schedule, 1):
        # 1. Перемена ПЕРЕД уроком
        if i > 1:
            prev_item = schedule[i-2]
            try:
                prev_end = prev_item['time'].split('-')[1].strip()
                curr_start = item['time'].split('-')[0].strip()
                t1 = datetime.strptime(prev_end, "%H:%M")
                t2 = datetime.strptime(curr_start, "%H:%M")
                diff = int((t2 - t1).total_seconds() / 60)
                if 0 < diff < 120:
                    text_parts.append(f"<i>   ☕️ Перемена {diff} мин</i>") # Убрал лишний \n
            except:
                pass

        # 2. Поиск задания
        hw_item = next((h for h in homeworks if h['subject'].lower() in item['subject'].lower() or item['subject'].lower() in h['subject'].lower()), None)
        
        num_emoji = ["0️⃣","1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"][i] if i <= 10 else f"{i}."
        room = f"каб. {item['room']}" if item['room'] else ""
        
        is_remote = "дистанц" in item.get('room', '').lower() or "дистанц" in item.get('subject', '').lower()
        remote_label = " 💻" if is_remote else ""
        
        is_ec = item.get('source') == 'EC'
        subj_icon = "📔" if is_ec else "📙"
        is_done = False
        
        if hw_item:
            desc = hw_item['description'].strip()
            hw_hash = hashlib.md5(f"{item['subject'].strip()}:{desc}".encode()).hexdigest()
            is_done = db.is_hw_completed(user['user_id'], date_str, hw_hash)
            if is_ec: subj_icon = "✅" if is_done else "🌟" 
            else:
                hw_type, _ = classify_hw(desc, "")
                if hw_type == "нет": subj_icon = "🕊️"
                else: subj_icon = "✅" if is_done else "❌"
        
        time_styled = f"<code>{item['time']}</code>"
        text_parts.append(f"{num_emoji} {time_styled} | {room}{remote_label}")
        text_parts.append(f"{subj_icon} <b>{html.escape(item['subject'].upper())}</b>")
        
        if is_ec:
            text_parts.append("   └ 🌟 Внеурочная деятельность")
        
        if not hw_item:
            text_parts.append("   └ 🕊️ <i>Без ДЗ</i>\n")
        else:
            desc = hw_item['description'].strip()
            found_links = [l.rstrip('.;:,') for l in re.findall(r'https?://\S+', desc)]
            clean_desc = re.sub(r'https?://\S+', '', desc).strip('; .')
            clean_desc = re.sub(r':\s*$', '', clean_desc).strip()
            
            # --- ПРОВЕРКА НА ПОВТОР ДЗ ---
            task_key = (item['subject'].lower().strip(), clean_desc)
            if task_key in unique_tasks_shown:
                prev_num = unique_tasks_shown[task_key]
                text_parts.append(f"   └ 🔄 ДЗ как на {prev_num} уроке\n")
                continue
            
            unique_tasks_shown[task_key] = i # Запоминаем номер первого появления
            
            if not clean_desc and not hw_item.get('materials') and not found_links:
                clean_desc = "Задание не указано"
            elif not clean_desc and (hw_item.get('materials') or found_links):
                clean_desc = "Задание по ссылке ниже"
            
            hw_type, type_icon = classify_hw(desc, "")
            status_task_icon = "✅" if is_done else type_icon
            text_parts.append(f"   └ {status_task_icon} <blockquote>{html.escape(clean_desc)}</blockquote>")
            
            all_links = []
            seen_urls = set()
            for m in hw_item.get('materials', []):
                l = m.get('link', '')
                if l and l not in seen_urls:
                    all_links.append(m); seen_urls.add(l)
            for l in found_links:
                l = l.rstrip('.,;:')
                if l not in seen_urls:
                    all_links.append({'title': 'Ссылка', 'link': l}); seen_urls.add(l)

            if all_links:
                for m in all_links:
                    m_title = html.escape(m.get('title', 'Материал'))
                    m_title = re.sub(r'^[⚡📎🔗]\s*', '', m_title)
                    m_link = m.get('link', '')
                    if m_link:
                        safe_link = html.escape(m_link)
                        
                        # Определяем иконку: Файл или Ссылка
                        is_file = m.get('type') == 'file' or any(m_link.lower().endswith(ext) for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.jpg', '.png', '.zip'])
                        
                        if is_file:
                            m_icon = "📎"
                            link_label = m_title
                        else:
                            m_icon = "⚡️" if any(x in m_link.lower() for x in ['edu-content', 'uchebnik', 'test', 'videouroki']) else "🔗"
                            link_label = "ПЕРЕЙТИ К ТЕСТУ" if m_icon == "⚡️" else m_title
                        
                        text_parts.append(f"     {m_icon} <a href='{safe_link}'><b>{link_label}</b></a>")
            text_parts.append("") 
        
    text_parts.append("──────────")

    # ─── СВОДКА И ПРОГРЕСС В КОНЦЕ ───
    total_tasks = len(all_unique_tasks)
    done_tasks = sum(1 for t in all_unique_tasks if t['is_done'])
    
    footer = ["\n📊 <b>ИТОГИ ДНЯ:</b>"]
    
    if total_tasks > 0:
        percent = int((done_tasks / total_tasks) * 100)
        filled = int(done_tasks / total_tasks * 10)
        bar = "🟢" * filled + "⚪" * (10 - filled)
        footer.append(f"📈 Прогресс: {bar} {percent}%")
        
        # Suggestion 2: Динамическая похвала
        if percent == 100:
            praise = "🥳 <b>ИДЕАЛЬНО! ТЫ ПОБЕДИЛ ЭТО ДЕНЬ!</b> 🔥"
        elif percent >= 80:
            praise = "🎯 <b>ФИНИШНАЯ ПРЯМАЯ! ЕЩЁ ЧУТЬ-ЧУТЬ!</b>"
        elif percent >= 50:
            praise = "⚡ <b>ХОРОШИЙ ТЕМП! БОЛЬШЕ ПОЛОВИНЫ ГОТОВО!</b>"
        elif percent >= 20:
            praise = "🚀 <b>ПОГНАЛИ! НАЧАЛО ПОЛОЖЕНО!</b>"
        else:
            praise = "☕ <b>ВРЕМЯ ПРИСТУПАТЬ К ДЕЛАМ!</b>"
        footer.append(praise)
            
        summary_lines = []
        if stats['тест'] > 0: summary_lines.append(f"⚡ {stats['тест']} тест(а)")
        if stats['теория'] > 0: summary_lines.append(f"📖 {stats['теория']} теория")
        if stats['письм.'] > 0: summary_lines.append(f"✍️ {stats['письм.']} письм.")
        if summary_lines:
            footer.append("📝 К выполнению: " + ", ".join(summary_lines))
            
        # Показываем внеурочку отдельно, если есть
        ec_tasks = [t for t in all_unique_tasks if t['is_ec']]
        if ec_tasks:
            done_ec = sum(1 for t in ec_tasks if t['is_done'])
            footer.append(f"🌟 Внеурочка: {done_ec}/{len(ec_tasks)} (по желанию)")
    else:
        footer.append("🕊️ На сегодня заданий нет!")

    text_parts.append("\n".join(footer))
    text_parts.append(f"\n🕒 Обновлено в {datetime.now().strftime('%H:%M:%S')}")

    # Сохраняем состояние
    await state.update_data(current_view_date=date_str)
    await state.set_state(BotStates.HOMEWORK_VIEW)

    # Клавиатура со статусами и кнопками ИИ
    inline_kb = get_hw_toggles_kb(all_unique_tasks, date_str)
    
    final_text = "\n".join(text_parts)
    
    if is_callback:
        try: await message.edit_text(final_text, reply_markup=inline_kb, parse_mode="HTML", disable_web_page_preview=True)
        except: await message.answer(final_text, reply_markup=inline_kb, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await message.answer(final_text, reply_markup=inline_kb, parse_mode="HTML", disable_web_page_preview=True)
    
    # Всегда обновляем нижние кнопки, если это не колбэк (или если нужно форсировать после изменений)
    if not is_callback:
        # get_hw_reply_kb() уже отправлен в hw_tomorrow или других местах, но для надежности:
        pass
        # Но обычно оно уже стоит с этапа выбора дат.

# ─── ОБРАБОТЧИКИ ───

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    if not db.get_user(message.from_user.id):
        db.create_user(message.from_user.id, first_name=message.from_user.first_name)
    await message.answer("👋 ДОБРО ПОЖАЛОВАТЬ В ПОМОЩНИК ЦДЗ!\n\nВЫБЕРИТЕ РАЗДЕЛ В МЕНЮ НИЖЕ:", reply_markup=get_main_menu_kb())
    await state.set_state(BotStates.MAIN_MENU)

@dp.message(F.text == "📚 МОЁ ДЗ")
async def my_hw_start(message: types.Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    if not await check_token(message, user): return
    # Навигация (Только Назад/Меню)
    await message.answer("📅 ВЫБЕРИТЕ НЕДЕЛЮ:", reply_markup=get_nav_reply_kb())
    await message.answer("📅 ДОСТУПНЫЕ ПЕРИОДЫ:", reply_markup=get_week_kb(prefix="manual"))
    await state.set_state(BotStates.WEEK_SELECTION)

@dp.callback_query(F.data.startswith("ai_solve_"))
async def process_inline_ai_solve(call: types.CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    action = parts[0]
    date_str = parts[1]
    
    if action == "ai_solve_all":
        await call.message.edit_text(f"🚀 ВСЁ ЦДЗ ({date_str}): Выберите точность решения:", 
                                 reply_markup=get_solve_accuracy_kb("all", date_str, is_batch=True))
    elif action == "ai_solve_select":
        await process_selective_solve_logic(call, state, override_date=date_str, is_edit=True)
    await call.answer()

@dp.message(F.text == "🧠 РЕШИТЬ ВСЁ [ЦДЗ]")
@dp.message(F.text == "🧠 РЕШИТЬ ВСЁ")
async def solve_all_text_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    date_str = data.get('current_view_date')
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')
    
    await message.answer(f"🚀 ВСЁ ЦДЗ ({date_str}): Выберите точность решения:", 
                         reply_markup=get_solve_accuracy_kb("all", date_str, is_batch=True))

@dp.message(F.text == "🔍 ВЫБОРОЧНО [ЦДЗ]")
@dp.message(F.text == "🔍 ВЫБОРОЧНО")
async def solve_select_text_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    date_str = data.get('current_view_date')
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')
    
    # Прямой вызов логики выбора предметов
    user = db.get_user(message.from_user.id)
    ps = ParserService()
    try:
        homeworks = await ps.get_mosreg_homework(user['token_mos'], user['student_id'], date_str, mesh_id=user.get('mesh_id'))
        if not homeworks:
            await message.answer("❌ На этот день заданий не найдено.")
            return
        
        kb_builder = InlineKeyboardBuilder()
        for hw in homeworks:
            desc = hw.get('description', '')[:30] + "..."
            subj = hw.get('subject', 'Предмет')
            kb_builder.button(text=f"🎯 {subj}: {desc}", callback_data=f"ai_select_subj:{hw['id']}:{date_str}")
        
        kb_builder.adjust(1)
        kb_builder.row(types.InlineKeyboardButton(text="🔙 НАЗАД", callback_data=f"back_to_hw:{date_str}"))
        
        await message.answer(f"🎯 Выберите задание для решения на {date_str}:", reply_markup=kb_builder.as_markup())
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(F.text == "⚡ АВТО РЕШЕНИЕ")
async def auto_solve_start(message: types.Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    if not await check_token(message, user): return
    await message.answer("🚀 АВТО-РЕЖИМ: ВЫБЕРИТЕ НЕДЕЛЮ:", reply_markup=get_week_kb(prefix="auto"))
    await state.set_state(BotStates.AUTO_SOLVE_WEEK)

@dp.message(F.text == "👤 ПРОФИЛЬ")
async def profile_main(message: types.Message, state: FSMContext, user_id: Optional[int] = None):
    target_id = user_id or message.from_user.id
    user = db.get_user(target_id)
    stats = db.get_stats(target_id)
    text = (
        f"👤 ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ\n━━━━━━━━━━━━━━━\n"
        f"📛 Имя: {user.get('first_name') or 'Не указано'}\n"
        f"🏫 Класс: {user.get('grade') or 'Не указан'}\n"
        f"🔑 Статус: {'✅ Подключен' if user.get('token_mos') else '❌ Не привязан'}\n"
        f"━━━━━━━━━━━━━━━\n📊 СТАТИСТИКА:\n"
        f"✅ Решено ДЗ: {stats['solved']}\n"
        f"⭐ Средний балл: {stats['avg']}\n"
    )
    if isinstance(message, types.Message):
        await message.answer(text, reply_markup=get_profile_kb())
    else: # Это CallbackQuery.message
        await message.edit_text(text, reply_markup=get_profile_kb())

@dp.message(F.text == "⚙️ НАСТРОЙКИ")
async def settings_start(message: types.Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    await message.answer(
        "⚙️ НАСТРОЙКИ БОТА:\n\n"
        "Здесь вы можете настроить параметры автоматизации под свои нужды.\n\n"
        "⏱ **Время решения**: Определяет паузу между выполнением тестов для имитации «человеческого» поведения.\n"
        "🎯 **Точность**: Позволяет выбрать желаемый процент правильных ответов (от 70% до 90%+).",
        reply_markup=get_settings_kb(user.get('solve_delay', 15), user.get('accuracy_mode', 'excellent')),
        parse_mode="Markdown"
    )
    await state.set_state(BotStates.SETTINGS)

@dp.message(F.text.startswith("📚 ДЗ НА"))
async def hw_tomorrow(message: types.Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    if not await check_token(message, user): return
    
    now = datetime.now()
    weekday = now.weekday()
    hour = now.hour
    
    # Умная логика (Синхронизировано с клавиатурой)
    if weekday == 4: # Пятница
        target_date = now if hour < 15 else now + timedelta(days=3)
    elif weekday == 5: # Суббота
        target_date = now + timedelta(days=2)
    elif weekday == 6: # Воскресенье
        target_date = now + timedelta(days=1)
    else: # Пн-Чт
        target_date = now if hour < 15 else now + timedelta(days=1)
        
    date_str = target_date.strftime('%Y-%m-%d')
    await state.update_data(selected_date=date_str)
    # Сначала ставим нижнее меню
    await message.answer(f"🔎 Загружаю {message.text}...", reply_markup=get_hw_reply_kb())
    await show_day_homework(message, user, date_str, state, is_callback=False)

@dp.callback_query(F.data.startswith("ai_solve_"))
async def process_inline_ai_solve(call: types.CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    action = parts[0]
    date_str = parts[1]
    
    if action == "ai_solve_all":
        await call.message.answer(f"🚀 ВСЁ ЦДЗ ({date_str}): Выберите точность решения:", 
                                reply_markup=get_solve_accuracy_kb("all", date_str, is_batch=True))
    elif action == "ai_solve_select":
        await process_selective_solve_logic(call.message, state, override_date=date_str)
    await call.answer()

@dp.callback_query(F.data.startswith("ai_select_subj:"))
async def process_ai_select_subj(call: types.CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    hw_id = parts[1]
    date_str = parts[2]
    await call.message.edit_text(f"🎯 Выберите точность решения для этого задания:", 
                               reply_markup=get_solve_accuracy_kb(hw_id, date_str))
    await call.answer()

@dp.callback_query(F.data.startswith("back_to_select_subj:"))
async def process_back_to_select_subj(call: types.CallbackQuery, state: FSMContext):
    date_str = call.data.split(":")[1]
    await process_selective_solve_logic(call, state, override_date=date_str, is_edit=True)
    await call.answer()

@dp.callback_query(F.data.startswith("task_acc:"))
@dp.callback_query(F.data.startswith("batch_acc:"))
@dp.callback_query(F.data.startswith("task_acc:"))
@dp.callback_query(F.data.startswith("batch_acc:"))
async def process_ai_select_accuracy_to_time(call: types.CallbackQuery):
    parts = call.data.split(":")
    if parts[0] == "task_acc":
        hw_id, accuracy, date_str = parts[1], parts[2], parts[3]
    else:
        hw_id, accuracy, date_str = "all", parts[1], parts[2]
        
    await process_ai_select_time_logic(call, hw_id, accuracy, date_str)

@dp.callback_query(F.data.startswith("select_time:"))
async def process_ai_select_time_callback(call: types.CallbackQuery):
    parts = call.data.split(":")
    hw_id, accuracy, date_str = parts[1], parts[2], parts[3]
    await process_ai_select_time_logic(call, hw_id, accuracy, date_str)

async def process_ai_select_time_logic(call: types.CallbackQuery, hw_id, accuracy, date_str):
    limit_info = "⌛ Ищу ограничение по времени..."
    await call.message.edit_text(f"⏱️ **На сколько минут растянуть решение?**\n\n{limit_info}", parse_mode="Markdown")
    
    limit = None
    if hw_id != "all":
        user = db.get_user(call.from_user.id)
        ps = ParserService()
        homeworks = await ps.get_mosreg_homework(user['token_mos'], user['student_id'], date_str, mesh_id=user.get('mesh_id'))
        target_hw = next((h for h in homeworks if str(h.get('id')) == hw_id), None)
        if target_hw:
            url_match = re.search(r'https?://\S+', target_hw.get('description', ''))
            if url_match:
                limit = await ps.get_test_limit(url_match.group(0))
    
    if limit:
        limit_text = f"❗ **ОГРАНИЧЕНИЕ ТЕСТА: {limit} МИН.**"
    else:
        limit_text = "ℹ️ Ограничение по времени не найдено или отсутствует."
        
    text = (f"⏱️ **На сколько минут растянуть решение?**\n\n"
            f"{limit_text}")
    
    await call.message.edit_text(text, parse_mode="Markdown",
                               reply_markup=get_solve_time_kb(hw_id, accuracy, date_str))
    await call.answer()

@dp.callback_query(F.data.startswith("sel_mode:"))
async def process_ai_select_final_mode(call: types.CallbackQuery):
    parts = call.data.split(":")
    hw_id, accuracy, mins, date_str = parts[1], parts[2], parts[3], parts[4]
    
    # Добавляем описание имитации сюда
    text = (f"🛠️ **Выберите режим решения:**\n\n"
            f"🎯 Выбрано время: **{mins} мин.**\n\n"
            "🤖 **Имитация человека:** бот сам меняет время ответа на каждый вопрос, "
            "чтобы поведение выглядело максимально естественно.")
            
    await call.message.edit_text(text, parse_mode="Markdown",
                               reply_markup=get_solve_final_mode_kb(hw_id, accuracy, mins, date_str))
    await call.answer()

@dp.callback_query(F.data.startswith("start_solve:"))
async def process_ai_start_solve(call: types.CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    # start_solve:hw_id:accuracy:mode:mins:date_str
    hw_id, accuracy, mode, mins, date_str = parts[1], parts[2], parts[3], parts[4], parts[5]
    
    is_human = (mode == "human")
    solve_delay = int(mins)
    
    # Конвертируем время
    solve_delay = int(mins)
    
    mode_text = "🤖 ИМИТАЦИЯ" if is_human else "⏱️ ОБЫЧНЫЙ"
    target_name = "ВСЕ ЦДЗ" if hw_id == "all" else f"Задание {hw_id[:8]}"
    msg = await call.message.edit_text(f"🚀 **НАЧИНАЮ РЕШЕНИЕ: {target_name}**\n\n"
                                f"🎯 Точность: {accuracy}\n"
                                f"⚙️ Режим: {mode_text}\n"
                                f"⏱️ Время: {mins} мин.\n\n"
                                f"⏳ Пожалуйста, подождите...", parse_mode="Markdown")
    
    user = db.get_user(call.from_user.id)
    ps = ParserService()
    
    try:
        hw_mesh_id = user.get('mesh_id')
        if hw_id == "all":
            # Решаем всё
            homeworks = await ps.get_mosreg_homework(user['token_mos'], user['student_id'], date_str, mesh_id=hw_mesh_id)
            total = len([h for h in homeworks if any(kw in h.get('description', '').lower() for kw in ['gosuslugi', 'test', 'edu-content'])])
            count = 0
            for hw in homeworks:
                desc = hw.get('description', '').lower()
                if any(kw in desc for kw in ['gosuslugi', 'test', 'edu-content']):
                    count += 1
                    target_url = hw.get('link') or ""
                    if not target_url:
                        url_match = re.search(r'https?://\S+', desc)
                        target_url = url_match.group(0) if url_match else ""
                        
                    if target_url:
                        await msg.edit_text(f"⏳ Решаю {count}/{total}: **{hw['subject']}**...")
                        await ps.solve_test(user['user_id'], target_url, accuracy_mode=accuracy, solve_delay_mins=solve_delay)
            
            await msg.answer("✅ Все доступные ЦДЗ решены!")
        else:
            # Решаем конкретное
            homeworks = await ps.get_mosreg_homework(user['token_mos'], user['student_id'], date_str, mesh_id=hw_mesh_id)
            target_hw = next((h for h in homeworks if str(h.get('id')) == hw_id), None)
            
            if not target_hw:
                await msg.edit_text("❌ Ошибка: Задание не найдено.")
                return
                
            target_url = target_hw.get('link') or ""
            if not target_url:
                url_match = re.search(r'https?://\S+', target_hw.get('description', ''))
                target_url = url_match.group(0) if url_match else ""
                
            if not target_url:
                await msg.edit_text("❌ Ошибка: Ссылка на тест не найдена.")
                return
            
            # Статус-колбэк для обновления сообщения
            async def status_update(text):
                try: await msg.edit_text(f"⏳ **{target_hw['subject']}**\n\n{text}", parse_mode="Markdown")
                except: pass

            res_text, result_data = await ps.solve_test(
                user['user_id'], url_match.group(0), 
                accuracy_mode=accuracy, solve_delay_mins=solve_delay,
                status_callback=status_update
            )
            
            # РЕЖИМ QR-ВХОДА
            if res_text == "NEEDS_QR":
                qr_path = result_data # В этом случае тут путь к скриншоту QR
                from aiogram.types import FSInputFile
                photo = FSInputFile(qr_path)
                
                qr_msg = await call.message.answer_photo(
                    photo,
                    caption="🔑 **ТРЕБУЕТСЯ АВТОРИЗАЦИЯ!**\n\n"
                            "Отсканируйте этот QR-код в приложении «Моя школа» или «Школьный портал» для продолжения решения теста.\n\n"
                            "⏳ *Бот ждет сканирования...*",
                    parse_mode="Markdown"
                )
                
                await state.update_data(
                    qr_msg_id=qr_msg.message_id,
                    solve_params={
                        'hw_id': hw_id,
                        'accuracy': accuracy,
                        'mode': mode,
                        'mins': mins,
                        'date_str': date_str,
                        'url': url_match.group(0)
                    }
                )
                await state.set_state(BotStates.WAITING_FOR_QR_SCAN)
                
                # Запускаем поллинг статуса QR
                asyncio.create_task(poll_qr_status(call.from_user.id, state, qr_msg))
                return

            screenshot_path = result_data
            if screenshot_path and os.path.exists(screenshot_path):
                # Сохраняем путь для колбэка прикрепления
                await state.update_data(last_screenshot=screenshot_path)
                
                # Отправляем скриншот
                from aiogram.types import FSInputFile
                photo = FSInputFile(screenshot_path)
                
                # Кнопки для прикрепления
                kb = InlineKeyboardBuilder()
                kb.button(text="✅ ДА, ПРИКРЕПИТЬ", callback_data=f"attach_yes:{hw_id}:{date_str}")
                kb.button(text="❌ НЕТ", callback_data="attach_no")
                kb.adjust(1)
                
                await call.message.answer_photo(
                    photo, 
                    caption=f"🏁 **{target_hw['subject']} РЕШЕНО!**\n\n{res_text}\n\n"
                            f"❓ Прикрепить скриншот к заданию в Школьном портале?",
                    reply_markup=kb.as_markup(),
                    parse_mode="Markdown"
                )
            else:
                await msg.edit_text(f"🏁 **{target_hw['subject']} РЕШЕНО!**\n\n{res_text}", parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Solve error: {e}")
        await msg.edit_text(f"❌ Произошла ошибка при решении: {str(e)[:100]}")
    
    # Сбрасываем состояние на HOMEWORK_VIEW, чтобы кнопки работали
    await state.set_state(BotStates.HOMEWORK_VIEW)
    await call.answer()

async def poll_qr_status(user_id, state, message):
    """Фоновый поллинг статуса QR-входа"""
    ps = ParserService()
    db_local = Database()
    
    for _ in range(30): # 30 попыток по 10 секунд (5 минут)
        await asyncio.sleep(10)
        
        # Проверяем, не сменил ли пользователь состояние вручную
        current_state = await state.get_state()
        if current_state != BotStates.WAITING_FOR_QR_SCAN:
            break
            
        status, token = await ps.check_qr_login_status(user_id)
        
        if status == "success":
            await message.edit_caption(caption="✅ **ВХОД ВЫПОЛНЕН!**\n\nПродолжаю решение теста...", parse_mode="Markdown")
            
            # Обновляем токен в БД если получили новый
            if token:
                db_local.update_user(user_id, token_mos=token)
            
            # Продолжаем решение
            data = await state.get_data()
            params = data.get('solve_params')
            if params:
                # Здесь вызываем solve_test повторно, он подхватит существующий браузер
                # Но для простоты реализации в этом прототипе — мы просто 
                # перекинем пользователя обратно на запуск, 
                # где parser.solve_test увидит активный браузер в self.active_browsers
                await state.set_state(BotStates.HOMEWORK_VIEW)
                # Имитируем нажатие кнопки Старт
                # (код ниже аналогичен process_ai_start_solve, но без первичного лоадинга)
                # Для удобства просто рекурсивно вызовем логику или попросим нажать кнопку снова.
                # Лучше — автоматически запустить.
                class FakeCall:
                    def __init__(self, uid, msg):
                        self.from_user = type('obj', (object,), {'id': uid})
                        self.message = msg
                        self.data = f"start_solve:{params['hw_id']}:{params['accuracy']}:{params['mode']}:{params['mins']}:{params['date_str']}"
                    async def answer(self): pass
                
                await process_ai_start_solve(FakeCall(user_id, message), state)
            return
            
        elif status in ["timeout", "expired", "error"]:
            await message.edit_caption(caption=f"❌ **ОШИБКА:** Тайм-аут или сессия закрыта. Попробуйте еще раз.", parse_mode="Markdown")
            await state.set_state(BotStates.HOMEWORK_VIEW)
            return

    await message.edit_caption(caption="❌ **ВРЕМЯ ИСТЕКЛО!** QR-код больше недействителен.", parse_mode="Markdown")
    await ps.close_qr_session(user_id)
    await state.set_state(BotStates.HOMEWORK_VIEW)

@dp.callback_query(F.data.startswith("attach_"))
async def process_attach_portal(call: types.CallbackQuery, state: FSMContext):
    if call.data == "attach_no":
        await call.message.edit_reply_markup(reply_markup=None)
        await call.answer("Ок, скриншот не будет прикреплен.")
        return
        
    parts = call.data.split(":")
    hw_id = parts[1]
    date_str = parts[2]
    
    await call.message.edit_caption(caption=call.message.caption + "\n\n⏳ *Прикрепляю к порталу...*", parse_mode="Markdown")
    
    data = await state.get_data()
    screenshot_path = data.get('last_screenshot')
    
    if not screenshot_path or not os.path.exists(screenshot_path):
        await call.message.edit_caption(caption=call.message.caption.split("⏳")[0] + "\n\n❌ **Ошибка:** Скриншот решения не найден.", parse_mode="Markdown", reply_markup=None)
        return

    success, result_msg = await parser.attach_screenshot_to_homework(
        call.from_user.id, hw_id, date_str, screenshot_path
    )
    
    if success:
        await call.message.edit_caption(caption=call.message.caption.split("⏳")[0] + f"\n\n✅ **{result_msg}**", parse_mode="Markdown", reply_markup=None)
    else:
        await call.message.edit_caption(caption=call.message.caption.split("⏳")[0] + f"\n\n❌ **Ошибка:** {result_msg}\nПопробуйте вручную.", parse_mode="Markdown", reply_markup=None)
        
    await state.set_state(BotStates.HOMEWORK_VIEW)
    await call.answer(result_msg)

# ─── CALLBACKS ───

@dp.callback_query(F.data == "back_to_main")
@dp.message(F.text == "🔙 НАЗАД")
@dp.message(F.text == "🏠 МЕНЮ")
async def back_to_main(event: types.Message | types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    
    # Если нажали "МЕНЮ", всегда идем в главное меню
    if isinstance(event, types.Message) and event.text == "🏠 МЕНЮ":
        await state.set_state(BotStates.MAIN_MENU)
        await event.answer("🏠 ГЛАВНОЕ МЕНЮ:", reply_markup=get_main_menu_kb())
        return

    if current_state == BotStates.HOMEWORK_VIEW:
        # Если мы в просмотре ДЗ, назад идет к выбору дня
        data = await state.get_data()
        offset = data.get('week_offset', 0)
        text = "📅 ВЫБЕРИТЕ ДЕНЬ:"
        kb = get_days_kb(offset, prefix="manual")
        
        if isinstance(event, types.CallbackQuery):
            await event.message.edit_text(text, reply_markup=kb)
        else:
            await event.answer(text, reply_markup=kb)
        await state.set_state(BotStates.DAY_SELECTION)
        return

    # Обычный возврат в меню
    await state.set_state(BotStates.MAIN_MENU)
    text = "🏠 ГЛАВНОЕ МЕНЮ:"
    kb = get_main_menu_kb()
    
    if isinstance(event, types.CallbackQuery):
        try: 
            await event.message.delete()
            await event.message.answer(text, reply_markup=kb)
        except: 
            await event.message.answer(text, reply_markup=kb)
    else:
        await event.answer(text, reply_markup=kb)

@dp.message(BotStates.HOMEWORK_VIEW, F.text.startswith("✅") | F.text.startswith("❌"))
async def process_hw_toggle_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    btn_map = data.get('hw_btn_map', {})
    
    task_info = btn_map.get(message.text)
    if not task_info:
        await message.answer("⚠️ Ошибка: Кнопка не распознана. Обновите список ДЗ.")
        return
        
    user = db.get_user(message.from_user.id)
    is_now_done = db.is_hw_completed(user['user_id'], task_info['date'], task_info['hash'])
    
    if is_now_done:
        db.unmark_hw_completed(user['user_id'], task_info['date'], task_info['hash'])
        await message.answer(f"🔄 Возвращено: {task_info['subject']}")
    else:
        db.mark_hw_completed(user['user_id'], task_info['date'], task_info['hash'])
        await message.answer(f"✅ Готово: {task_info['subject']}")
        
    # Обновляем вид
    await show_day_homework(message, user, task_info['date'], state, is_callback=False)

@dp.message(F.text == "🧠 РЕШИТЬ ВСЁ [ЦДЗ]")
@dp.message(BotStates.HOMEWORK_VIEW, F.text == "🧠 РЕШИТЬ ВСЁ [ЦДЗ]")
async def process_batch_solve_text_redirect(message: types.Message, state: FSMContext):
    data = await state.get_data()
    date_str = data.get('current_view_date')
    if not date_str: return
    await message.answer(f"🚀 ВСЁ ЦДЗ ({date_str}): Выберите точность решения:", 
                        reply_markup=get_solve_accuracy_kb("all", date_str, is_batch=True))

@dp.message(F.text == "🔍 ВЫБОРОЧНО [ЦДЗ]")
@dp.message(BotStates.HOMEWORK_VIEW, F.text == "🔍 ВЫБОРОЧНО [ЦДЗ]")
async def process_selective_solve_text_redirect(message: types.Message, state: FSMContext):
    await process_selective_solve_logic(message, state)

async def process_selective_solve_logic(event: types.Message | types.CallbackQuery, state: FSMContext, override_date: Optional[str] = None, is_edit: bool = False):
    data = await state.get_data()
    date_str = override_date or data.get('current_view_date')
    if not date_str:
        # Пытаемся определить дату (сегодня или завтра в зависимости от времени)
        now = datetime.now()
        if now.hour >= 15:
            d = now + timedelta(days=1)
            # Пропуск выходных для дефолта
            if d.weekday() == 5: d += timedelta(days=2)
            elif d.weekday() == 6: d += timedelta(days=1)
        else:
            d = now
            if d.weekday() == 5: d += timedelta(days=2)
            elif d.weekday() == 6: d += timedelta(days=1)
        date_str = d.strftime('%Y-%m-%d')
        await state.update_data(current_view_date=date_str)
    
    user_id = event.from_user.id
    user = db.get_user(user_id)
    ps = ParserService()
    
    # Загружаем и домашку, и расписание для кросс-чека
    hw_mesh_id = user.get('mesh_id')
    homeworks = await ps.get_mosreg_homework(user['token_mos'], user['student_id'], date_str, mesh_id=hw_mesh_id)
    schedule = await ps.get_mosreg_schedule(user['token_mos'], user['student_id'], date_str, mesh_id=hw_mesh_id)
    
    logger.info(f"Selective solve: found {len(schedule or [])} lessons and {len(homeworks or [])} homeworks for {date_str}")
    
    kb = InlineKeyboardBuilder()
    found_any = False
    added_subjects = set()
    
    for item in (schedule or []):
        subj_name = item['subject'].lower().strip()
        # Ищем ДЗ для этого предмета из расписания
        hw = next((h for h in homeworks if h['subject'].lower().strip() in subj_name or subj_name in h['subject'].lower().strip()), None)
        
        logger.info(f"Checking subject: {subj_name}, homework found: {hw is not None}")
        
        if hw and hw['subject'] not in added_subjects:
            desc = hw.get('description', '').strip()
            url_match = re.search(r'https?://\S+', desc)
            url = url_match.group(0) if url_match else ""
            
            hw_type, _ = classify_hw(desc, url)
            logger.info(f"Subject {hw['subject']} type: {hw_type}, desc: {desc[:50]}")
            
            # Проверяем наличие ЦДЗ
            if hw_type == "тест":
                kb.button(text=f"🔹 {hw['subject']}", callback_data=f"ai_select_subj:{hw['id']}:{date_str}")
                found_any = True
                added_subjects.add(hw['subject'])
            
    msg = event.message if isinstance(event, types.CallbackQuery) else event
    
    if not found_any:
        await msg.answer("ℹ️ На этот день не найдено подходящих ЦДЗ для автоматического решения.")
        return

    kb.adjust(1)
    text = "🎯 Выберите конкретное ЦДЗ для решения:"
    
    if is_edit:
        await msg.edit_text(text, reply_markup=kb.as_markup())
    else:
        await msg.answer(text, reply_markup=kb.as_markup())

@dp.message(BotStates.HOMEWORK_VIEW, F.text == "🔄 ОБНОВИТЬ")
async def process_refresh_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    date_str = data.get('current_view_date')
    if not date_str: return
    
    user = db.get_user(message.from_user.id)
    await message.answer("🔄 Обновляю список заданий...")
    await show_day_homework(message, user, date_str, state, is_callback=False)

@dp.callback_query(F.data.startswith("back_to_weeks_"))
async def back_to_weeks(call: types.CallbackQuery, state: FSMContext):
    prefix = call.data.replace("back_to_weeks_", "")
    await state.set_state(BotStates.WEEK_SELECTION if "manual" in prefix else BotStates.AUTO_SOLVE_WEEK)
    await call.message.edit_text("📅 ВЫБЕРИТЕ НЕДЕЛЮ:", reply_markup=get_week_kb(prefix=prefix))

@dp.callback_query(F.data == "back_to_days")
async def back_to_days_handler(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await call.message.edit_text("📅 ВЫБЕРИТЕ ДЕНЬ:", reply_markup=get_days_kb(data.get('week_offset', 0), prefix="manual"))

@dp.callback_query(StateFilter(BotStates.WEEK_SELECTION, BotStates.AUTO_SOLVE_WEEK), F.data.contains("_prev") | F.data.contains("_curr") | F.data.contains("_next"))
async def week_select(call: types.CallbackQuery, state: FSMContext):
    prefix = "manual" if "manual" in call.data else "auto"
    if "_curr" in call.data:
        offset = 0
    elif "_next" in call.data:
        offset = 1
    else: # _prev
        offset = -1
    await state.update_data(week_offset=offset)
    await state.set_state(BotStates.DAY_SELECTION if prefix == "manual" else BotStates.AUTO_SOLVE_DAY)
    # Suggestion: Убрали лишнее текстовое сообщение, Reply-клавиатура и так на месте
    await call.message.edit_text("📅 ВЫБЕРИТЕ ДЕНЬ:", reply_markup=get_days_kb(offset, prefix=prefix))

@dp.callback_query(F.data.startswith("manual_"))
@dp.callback_query(F.data.startswith("refresh_day_"))
@dp.callback_query(F.data.startswith("refresh_hw_list:"))
async def process_refresh_day(call: types.CallbackQuery, state: FSMContext):
    if ":" in call.data: # формат refresh_hw_list:date
        date_str = call.data.split(":")[1]
        is_refresh = True
    else: # форматы manual_date или refresh_day_date_source
        parts = call.data.split("_")
        date_str = parts[1] if "manual" in call.data else parts[2]
        is_refresh = "refresh" in call.data
        
    await state.update_data(selected_date=date_str)
    user = db.get_user(call.from_user.id)
    await show_day_homework(call.message, user, date_str, state, is_callback=True)

@dp.callback_query(F.data.startswith("hw_done:"))
async def process_hw_done(callback: types.CallbackQuery, state: FSMContext):
    # data: hw_done:date:hash
    parts = callback.data.split(':')
    date_str = parts[1]
    hw_hash = parts[2]
    
    user = db.get_user(callback.from_user.id)
    # ПЕРЕКЛЮЧЕНИЕ: Если уже сделано — убираем, если нет — ставим
    is_now_done = db.is_hw_completed(user['user_id'], date_str, hw_hash)
    
    if is_now_done:
        db.unmark_hw_completed(user['user_id'], date_str, hw_hash)
        await callback.answer("❌ Задание отмечено как НЕВЫПОЛНЕННОЕ")
    else:
        db.mark_hw_completed(user['user_id'], date_str, hw_hash)
        await callback.answer("✅ Задание выполнено!")
        
    # Обновляем вид
    await show_day_homework(callback.message, user, date_str, state, is_callback=True)

@dp.callback_query(F.data.startswith("refresh_hw_list:"))
async def refresh_hw_list(call: types.CallbackQuery, state: FSMContext):
    date_str = call.data.split(":")[1]
    user = db.get_user(call.from_user.id)
    await call.answer("🔄 Обновляю данные...")
    await show_day_homework(call.message, user, date_str, state, is_callback=True)

@dp.callback_query(F.data.startswith("batch_solve_pre_"))
async def batch_solve_pre_handler(call: types.CallbackQuery):
    date_str = call.data.replace("batch_solve_pre_", "")
    await call.message.edit_text(f"🚀 ВЫБЕРИТЕ РЕЖИМ РЕШЕНИЯ ДЛЯ {date_str}:", reply_markup=get_batch_solve_pre_kb(date_str))

@dp.callback_query(F.data.startswith("batch_solve_"))
async def batch_solve_handler(call: types.CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    date_str, mode = parts[2], parts[3]
    user = db.get_user(call.from_user.id)
    try:
        homeworks = await parser.get_mosreg_homework(user['token_mos'], user['student_id'], date_str, mesh_id=user.get('mesh_id'))
    except MosregAuthError:
        await call.message.edit_text(
            "⚠️ ВАША СЕССИЯ ИСТЕКЛА!\n\nТОКЕН БОЛЬШЕ НЕ ДЕЙСТВИТЕЛЕН. ПОЖАЛУЙСТА, ОБНОВИТЕ ЕГО:\n"
            "🔗 [ПОЛУЧИТЬ НОВЫЙ ТОКЕН](https://authedu.mosreg.ru/v2/token/refresh)\n\n"
            "ПРОСТО ОТПРАВЬТЕ НОВЫЙ ТОКЕН МНЕ.",
            reply_markup=InlineKeyboardBuilder().button(text="🔙 В МЕНЮ", callback_data="back_to_main").as_markup(),
            parse_mode="Markdown"
        )
        return
    
    if not homeworks:
        await call.answer("❌ НЕТ ЗАДАНИЙ ДЛЯ РЕШЕНИЯ", show_alert=True)
        return

    await call.answer("🚀 НАЧИНАЮ МАССОВОЕ РЕШЕНИЕ...")
    total = len(homeworks)
    for i, hw in enumerate(homeworks, 1):
        if not hw.get('link'): continue
        rem = user.get('solve_delay', 15) * (total - i + 1)
        await call.message.edit_text(f"⏳ В ПРОЦЕССЕ ВЫПОЛНЕНИЯ ({i}/{total})\n📚 ПРЕДМЕТ: {hw['subject'].upper()}\n🕒 ОСТАЛОСЬ: {rem} МИН")
        await parser.solve_test(call.from_user.id, hw['link'])
        
    await call.message.answer("🎉 ВСЕ ЗАДАНИЯ ВЫПОЛНЕНЫ!", reply_markup=get_main_menu_kb())

@dp.callback_query(F.data.startswith("selective_solve_"))
async def selective_solve_handler(call: types.CallbackQuery, state: FSMContext):
    date_str = call.data.replace("selective_solve_", "")
    user = db.get_user(call.from_user.id)
    try:
        hws = await parser.get_mosreg_homework(user['token_mos'], user['student_id'], date_str)
    except MosregAuthError:
        await call.message.edit_text(
            "⚠️ ВАША СЕССИЯ ИСТЕКЛА!\n\nТОКЕН БОЛЬШЕ НЕ ДЕЙСТВИТЕЛЕН. ПОЖАЛУЙСТА, ОБНОВИТЕ ЕГО:\n"
            "🔗 [ПОЛУЧИТЬ НОВЫЙ ТОКЕН](https://authedu.mosreg.ru/v2/token/refresh)\n\n"
            "ПРОСТО ОТПРАВЬТЕ НОВЫЙ ТОКЕН МНЕ.",
            reply_markup=InlineKeyboardBuilder().button(text="🔙 В МЕНЮ", callback_data="back_to_main").as_markup(),
            parse_mode="Markdown"
        )
        return
    builder = InlineKeyboardBuilder()
    for i, hw in enumerate(hws):
        if hw.get('link'): builder.button(text=f"📝 {hw['subject'].upper()}", callback_data=f"solve_task_{i}_{date_str}")
    builder.button(text="🔙 НАЗАД", callback_data=f"refresh_day_{date_str}_manual")
    builder.adjust(1)
    await call.message.edit_text("🔍 ВЫБЕРИТЕ ПРЕДМЕТ:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("solve_task_"))
async def solve_task_handler(call: types.CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    idx, date_str = int(parts[2]), parts[3]
    user = db.get_user(call.from_user.id)
    try:
        hws = await parser.get_mosreg_homework(user['token_mos'], user['student_id'], date_str)
    except MosregAuthError:
        await call.answer("⚠️ СЕССИЯ ИСТЕКЛА", show_alert=True)
        return
    hw = hws[idx]
    await call.message.edit_text(f"🧩 НАЧИНАЮ РЕШЕНИЕ: {hw['subject'].upper()}...")
    res = await parser.solve_test(call.from_user.id, hw['link'])
    await call.message.answer(f"🏁 {hw['subject'].upper()}: {res}")

@dp.callback_query(F.data == "refresh_data")
async def refresh_user_data(call: types.CallbackQuery):
    user = db.get_user(call.from_user.id)
    if not user.get('token_mos'): return await call.answer("⚠️ НУЖЕН ТОКЕН!", show_alert=True)
    await call.answer("⏳ ОБНОВЛЯЮ...")
    profile = await parser.fetch_mosreg_profile(user['token_mos'])
    if profile:
        db.update_user(call.from_user.id, 
                       first_name=profile['first_name'], 
                       grade=profile.get('grade', ''), 
                       student_id=profile['student_id'],
                       mesh_id=profile.get('mesh_id'))
        await call.message.answer("✅ ДАННЫЕ ОБНОВЛЕНЫ!")
    else: await call.answer("❌ ОШИБКА ОБНОВЛЕНИЯ", show_alert=True)

@dp.callback_query(F.data == "set_speed_menu")
async def speed_menu(call: types.CallbackQuery):
    user = db.get_user(call.from_user.id)
    await call.message.edit_text("⏱ ВЫБЕРИТЕ ВРЕМЯ РЕШЕНИЯ:", reply_markup=get_speed_kb(user.get('solve_delay', 15)))

@dp.callback_query(F.data.startswith("save_speed_"))
async def save_speed(call: types.CallbackQuery):
    speed = int(call.data.replace("save_speed_", ""))
    db.update_user(call.from_user.id, solve_delay=speed)
    await call.answer(f"✅ УСТАНОВЛЕНО: {speed} МИН")
    await call.message.edit_reply_markup(reply_markup=get_speed_kb(speed))

@dp.callback_query(F.data == "set_accuracy_menu")
async def accuracy_menu(call: types.CallbackQuery):
    user = db.get_user(call.from_user.id)
    await call.message.edit_text("🎯 ВЫБЕРИТЕ ТОЧНОСТЬ:", reply_markup=get_accuracy_kb(user.get('accuracy_mode', 'advanced')))

@dp.callback_query(F.data.startswith("save_acc_"))
async def save_accuracy(call: types.CallbackQuery):
    mode = call.data.replace("save_acc_", "")
    db.update_user(call.from_user.id, accuracy_mode=mode)
    await call.answer("✅ ТОЧНОСТЬ ОБНОВЛЕНА")
    await call.message.edit_reply_markup(reply_markup=get_accuracy_kb(mode))

@dp.message(F.text.startswith("eyJ"))
async def process_token(message: types.Message, state: FSMContext):
    token = message.text.strip()
    msg = await message.answer("🔍 ПРОВЕРКА ТОКЕНА...")
    profile = await parser.fetch_mosreg_profile(token)
    if profile:
        db.update_user(message.from_user.id, 
                       token_mos=token, 
                       first_name=profile['first_name'], 
                       grade=profile.get('grade', ''), 
                       student_id=profile['student_id'],
                       mesh_id=profile.get('mesh_id'))
        await msg.delete()
        await message.answer(f"✅ УСПЕШНО! ПРИВЕТ, {profile['first_name']}!", reply_markup=get_main_menu_kb())
        await state.set_state(BotStates.MAIN_MENU)
    else:
        await msg.edit_text("❌ ОШИБКА! ТОКЕН НЕВЕРЕН.")

@dp.callback_query(F.data == "what_is_token")
async def explain_token(call: types.CallbackQuery):
    await call.message.edit_text("🔑 ТОКЕН — ЭТО ВАШ ЦИФРОВОЙ КЛЮЧ ДЛЯ ДОСТУПА К ТЕСТАМ. БЕЗОПАСНО И БЫСТРО.", 
                                 reply_markup=InlineKeyboardBuilder().button(text="🔙 НАЗАД", callback_data="back_to_main").as_markup())

@dp.callback_query(F.data == "subscription_info")
async def subscription_info(call: types.CallbackQuery):
    await call.message.edit_text("💳 ПОДПИСКА ПРЕМИУМ\n\n💎 ЦЕНА: 299₽ / МЕСЯЦ\n\nПИШИТЕ: @admin_username", 
                                 reply_markup=InlineKeyboardBuilder().button(text="🔙 НАЗАД", callback_data="back_to_settings").as_markup())

@dp.callback_query(F.data == "back_to_settings")
async def back_to_settings(call: types.CallbackQuery):
    user = db.get_user(call.from_user.id)
    await call.message.edit_text("⚙️ НАСТРОЙКИ БОТА:", reply_markup=get_settings_kb(user.get('solve_delay', 15), user.get('accuracy_mode', 'excellent')))

@dp.callback_query(F.data == "refresh_profile_data")
async def refresh_profile_data(call: types.CallbackQuery, state: FSMContext):
    user = db.get_user(call.from_user.id)
    if not user or not user.get('token_mos'):
        await call.answer("⚠️ ОШИБКА: ТОКЕН НЕ НАЙДЕН", show_alert=True)
        return
        
    await call.answer("🔄 ОБНОВЛЯЮ ДАННЫЕ...", show_alert=False)
    try:
        # Пытаемся получить свежий профиль
        new_prof = await parser.fetch_mosreg_profile(user['token_mos'])
        if new_prof:
            db.update_user(
                call.from_user.id,
                first_name=new_prof.get('first_name'),
                last_name=new_prof.get('last_name'),
                grade=new_prof.get('grade'),
                student_id=new_prof.get('student_id')
            )
            await call.answer("✅ ПРОФИЛЬ ОБНОВЛЕН!", show_alert=True)
            # Перерисовываем профиль
            await profile_main(call.message, state, user_id=call.from_user.id)
        else:
            await call.answer("❌ НЕ УДАЛОСЬ ПОЛУЧИТЬ ДАННЫЕ", show_alert=True)
    except Exception as e:
        logger.error(f"Error refreshing profile: {e}")
        await call.answer(f"❌ ОШИБКА: {str(e)[:50]}", show_alert=True)

@dp.callback_query(F.data == "delete_token_confirm")
async def delete_token_confirm(call: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ ДА, УДАЛИТЬ", callback_data="delete_token_final")
    builder.button(text="❌ ОТМЕНА", callback_data="back_to_main")
    builder.adjust(2)
    await call.message.edit_text("⚠️ ВЫ УВЕРЕНЫ, ЧТО ХОТИТЕ УДАЛИТЬ ТОКЕН?", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "delete_token_final")
async def delete_token_final(call: types.CallbackQuery, state: FSMContext):
    db.update_user(call.from_user.id, token_mos=None)
    await call.answer("🗑 ТОКЕН УДАЛЕН", show_alert=True)
    await back_to_main(call, state)

# ─── ФОНОВОЕ ОБНОВЛЕНИЕ ───

# PID file management
PID_FILE = "bot.pid"

def create_pid_file():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                pid = f.read().strip()
            # Check if process is actually running using tasklist
            import subprocess
            output = subprocess.check_output(f'tasklist /FI "PID eq {pid}"', shell=True).decode('cp866')
            if pid in output:
                logger.error(f"Bot is already running (PID: {pid}). Exiting.")
                return False
        except Exception:
            pass
    
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
    return True

def remove_pid_file():
    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except:
            pass

async def token_refresher_task(parser_service):
    """Фоновая задача для автоматического обновления токенов каждые 40 минут."""
    while True:
        try:
            logger.info("Starting background token refresh cycle...")
            users = db.get_all_users_with_tokens()
            for u in users:
                try:
                    new_token = await parser_service.refresh_token(u['token_mos'])
                    if new_token:
                        db.update_user(u['user_id'], token_mos=new_token)
                        logger.info(f"Refreshed token for user {u['user_id']}")
                    else:
                        logger.warning(f"Could not refresh token for user {u['user_id']} (no response)")
                except MosregAuthError:
                    logger.warning(f"Token for user {u['user_id']} is dead. Stopping refresher for this user.")
                
                await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Refresher task error: {e}")
        
        await asyncio.sleep(40 * 60)

async def main():
    if not create_pid_file():
        return

    logger.info("Bot starting...")
    import aiohttp
    
    async with aiohttp.ClientSession() as shared_session:
        # Update parser to use the shared session
        parser.session = shared_session
        
        # Start background tasks
        refresher = asyncio.create_task(token_refresher_task(parser))
        
        try:
            await dp.start_polling(bot)
        finally:
            refresher.cancel()
            remove_pid_file()
            logger.info("Bot stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        remove_pid_file()
