import asyncio
import logging
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup

from database import Database
from parser import ParserService

from aiogram.client.session.aiohttp import AiohttpSession

load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и БД
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8684063011:AAG5xtd4MfZLIc3FvGbXCABLnh-hcpieR_U")
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
    STATS = State()
    ABOUT = State()
    SUPPORT = State()
    WAITING_FOR_TOKEN = State()

# ─── КЛАВИАТУРЫ ───

def get_main_menu_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📚 Моё ДЗ")
    builder.button(text="⚡ Авто решение")
    builder.button(text="👤 Профиль")
    builder.button(text="⚙️ Настройки")
    builder.button(text="📡 О нас")
    builder.button(text="💬 Поддержка")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_week_kb(prefix="week"):
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Предыдущая", callback_data=f"{prefix}_prev")
    builder.button(text="📅 Текущая", callback_data=f"{prefix}_curr")
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    builder.adjust(2, 1)
    return builder.as_markup()

def get_days_kb(week_offset=0, prefix="day"):
    builder = InlineKeyboardBuilder()
    today = datetime.now()
    # Находим понедельник текущей недели
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    
    days_ru = ["Пн", "Вт", "Ср", "Чт", "Пт"]
    for i in range(5):
        d = monday + timedelta(days=i)
        date_str = d.strftime('%Y-%m-%d')
        display_str = f"{days_ru[i]} {d.strftime('%d.%m')}"
        builder.button(text=display_str, callback_data=f"{prefix}_{date_str}")
    
    builder.button(text="🔙 Назад", callback_data=f"back_to_weeks_{prefix}")
    builder.adjust(3, 2, 1)
    return builder.as_markup()

def get_hw_action_kb(subject_name):
    builder = InlineKeyboardBuilder()
    builder.button(text="🧠 Решать (Точно)", callback_data=f"solve_precise_{subject_name}")
    builder.button(text="⚡ Решать (Быстро)", callback_data=f"solve_fast_{subject_name}")
    builder.button(text="🔄 Обновить", callback_data="refresh_hw")
    builder.button(text="🔙 Назад", callback_data="back_to_days")
    builder.adjust(2, 2)
    return builder.as_markup()

def get_settings_kb(solve_delay=15, accuracy_mode="excellent"):
    accuracy_map = {"modest": "Обычный (80%)", "advanced": "Перспективный (90%)", "excellent": "Отличник (100%)"}
    acc_text = accuracy_map.get(accuracy_mode, "Отличник (100%)")
    
    builder = InlineKeyboardBuilder()
    builder.button(text=f"⏱ Скорость: {solve_delay} мин", callback_data="set_speed_menu")
    builder.button(text=f"🎯 Точность: {acc_text}", callback_data="set_accuracy_menu")
    builder.button(text="🔄 Обновить данные", callback_data="refresh_data")
    builder.button(text="💳 Подписка", callback_data="subscription_info")
    builder.button(text="🔙 Вернуться в главное меню", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_speed_kb():
    builder = InlineKeyboardBuilder()
    speeds = [1, 5, 10, 15, 20, 25]
    for s in speeds:
        builder.button(text=f"{s} мин", callback_data=f"save_speed_{s}")
    builder.button(text="🔙 Назад", callback_data="back_to_settings")
    builder.adjust(3, 3, 1)
    return builder.as_markup()

def get_accuracy_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🥉 Обычный (80%)", callback_data="save_acc_modest")
    builder.button(text="🥈 Перспективный (90%)", callback_data="save_acc_advanced")
    builder.button(text="🥇 Отличник (100%)", callback_data="save_acc_excellent")
    builder.button(text="🔙 Назад", callback_data="back_to_settings")
    builder.adjust(1)
    return builder.as_markup()

# ─── ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ───

def get_token_help_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="Что такое токен ❓", callback_data="what_is_token")
    builder.button(text="🔙 Вернуться в главное меню", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

async def check_token(message: types.Message, user):
    if not user or not user.get('token_mos'):
        help_text = (
            "⚠️ **Токен не загружен!**\n\n"
            "Токен — это твой цифровой ключ! Он дает боту доступ к тестам! 🔑\n\n"
            "**Как получить токен:**\n\n"
            "1️⃣ **Перейди по ссылке:**\n"
            "- [Москва](https://school.mos.ru/?backUrl=https%3A%2F%2Fschool.mos.ru%2Fv2%2Ftoken%2Frefresh)\n"
            "- **Для Московской области:**\n"
            "   • [Войти в аккаунт](https://authedu.mosreg.ru/)\n"
            "   • [Получить токен](https://authedu.mosreg.ru/v2/token/refresh)\n\n"
            "2️⃣ **Введи логин и пароль** от своего аккаунта.\n"
            "(Не волнуйся, мы их не видим — это только для системы! 🔒)\n\n"
            "3️⃣ **Скопируй токен** с открывшейся страницы.\n"
            "(Он начинается с `eyJhbG...` — как секретный код! 🕵️‍♂️)\n\n"
            "4️⃣ **Отправь токен сюда**, и наш бот сразу приступит к работе! 🚀\n\n"
            "P.S. Без токена — никаких тестов. Так что действуй! 🔥\n"
            "*Для МО обязательно сначала войти в аккаунт, а потом получить токен!*"
        )
        if isinstance(message, types.CallbackQuery):
            await message.message.answer(help_text, parse_mode="Markdown", reply_markup=get_token_help_kb(), disable_web_page_preview=True)
        else:
            await message.answer(help_text, parse_mode="Markdown", reply_markup=get_token_help_kb(), disable_web_page_preview=True)
        return False
    return True

# ─── ОБРАБОТЧИКИ КОМАНД ───

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = db.get_user(message.from_user.id)
    if not user:
        db.create_user(message.from_user.id, first_name=message.from_user.first_name)
    
    await message.answer(
        "👋 **Добро пожаловать в Продвинутый Помощник ЦДЗ!**\n\n"
        "Я помогу тебе с расписанием и автоматическим решением тестов.\n"
        "Выбери раздел в меню ниже:",
        reply_markup=get_main_menu_kb(),
        parse_mode="Markdown"
    )
    await state.set_state(BotStates.MAIN_MENU)

@dp.message(Command("restart"))
async def cmd_restart(message: types.Message, state: FSMContext):
    db.delete_user(message.from_user.id)
    await cmd_start(message, state)

# ─── ГЛАВНОЕ МЕНЮ ───

@dp.message(F.text == "📚 Моё ДЗ")
async def my_hw_start(message: types.Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    if not await check_token(message, user): return
    
    await message.answer("📅 **Выберите неделю:**", reply_markup=get_week_kb(prefix="manual"))
    await state.set_state(BotStates.WEEK_SELECTION)

@dp.message(F.text == "⚡ Авто решение")
async def auto_solve_start(message: types.Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    if not await check_token(message, user): return
    
    await message.answer("🚀 **Авто-режим: Выберите неделю:**", reply_markup=get_week_kb(prefix="auto"))
    await state.set_state(BotStates.AUTO_SOLVE_WEEK)

@dp.message(F.text == "👤 Профиль")
async def profile_main(message: types.Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    stats = db.get_stats(message.from_user.id)
    
    status_icon = "✅" if user.get('token_mos') else "❌"
    status_text = "Привязан" if user.get('token_mos') else "Не привязан"
    
    profile_text = (
        f"👤 **Профиль пользователя**\n"
        f"──────────────────\n"
        f"📛 Имя: {user.get('first_name') or 'хлеб'}\n"
        f"🏫 Класс: {user.get('grade') or 'Не указан'}\n"
        f"🔑 Статус: {status_icon} {status_text}\n"
        f"──────────────────\n"
        f"📊 **Статистика:**\n"
        f"✅ Решено ДЗ: {stats['solved']}\n"
        f"⭐ Средний балл: {stats['avg']}\n"
    )
    await message.answer(profile_text, parse_mode="Markdown")

@dp.message(F.text == "📊 Статистика")
async def stats_redirect(message: types.Message, state: FSMContext):
    # Если нажал старую кнопку (в кеше телеграма), шлем в профиль
    await profile_main(message, state)

@dp.message(F.text == "📡 О нас")
async def about_main(message: types.Message, state: FSMContext):
    await message.answer(
        "📡 **О проекте**\n\n"
        "Этот бот создан для помощи ученикам в автоматизации ЦДЗ.\n"
        "Мы используем ИИ Gemini и Playwright для решения тестов.\n\n"
        "📢 Канал: @your_channel\n"
        "👥 Разработчик: @developer"
    )

@dp.message(F.text == "💬 Поддержка")
@dp.message(F.text == "💳 Поддержка")
async def support_main(message: types.Message, state: FSMContext):
    await message.answer(
        "💬 **Чат поддержки**\n\n"
        "Если у тебя возникли вопросы или проблемы в работе бота, пиши нам в чат!\n\n"
        "🔗 Ссылка: [Перейти в чат](https://t.me/your_support_chat)",
        parse_mode="Markdown"
    )

@dp.message(F.text == "⚙️ Настройки")
async def settings_start(message: types.Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    await message.answer(
        "⚙️ **Настройки бота:**\n\n"
        "Здесь можно настроить скорость решения тестов и желаемую точность ответов.",
        reply_markup=get_settings_kb(user.get('solve_delay', 15), user.get('accuracy_mode', 'excellent'))
    )
    await state.set_state(BotStates.SETTINGS)

# ─── CALLBACK ХЕНДЛЕРЫ ───

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.MAIN_MENU)
    # Пытаемся отредактировать сообщение или отправить новое если это из 'check_token'
    try:
        await call.message.edit_text("🏠 **Главное меню:**", reply_markup=get_main_menu_kb(), parse_mode="Markdown")
    except:
        await call.message.answer("🏠 **Главное меню:**", reply_markup=get_main_menu_kb(), parse_mode="Markdown")

# Выбор недели (Ручной / Авто)
@dp.callback_query(StateFilter(BotStates.WEEK_SELECTION, BotStates.AUTO_SOLVE_WEEK), F.data.contains("_prev") | F.data.contains("_curr"))
async def week_select(call: types.CallbackQuery, state: FSMContext):
    prefix = "manual" if "manual" in call.data else "auto"
    offset = 0 if "curr" in call.data else -1
    await state.update_data(week_offset=offset)
    next_state = BotStates.DAY_SELECTION if prefix == "manual" else BotStates.AUTO_SOLVE_DAY
    await state.set_state(next_state)
    await call.message.edit_text("📅 **Выберите день:**", reply_markup=get_days_kb(offset, prefix=prefix), parse_mode="Markdown")

# Выбор дня -> Мои ЦДЗ (Ручной)
@dp.callback_query(BotStates.DAY_SELECTION, F.data.startswith("manual_"))
async def manual_day_select(call: types.CallbackQuery, state: FSMContext):
    date_str = call.data.replace("manual_", "")
    await state.update_data(selected_date=date_str)
    
    user = db.get_user(call.from_user.id)
    if not user or not user.get('token_mos'):
        await call.message.answer("⚠️ Токен не найден. Пришлите токен в чат!")
        await state.set_state(BotStates.WAITING_FOR_TOKEN)
        return

    msg = await call.message.edit_text(f"⏳ **Загружаю расписание на {date_str}...**", parse_mode="Markdown")
    
    schedule = await parser.get_mosreg_schedule(user['token_mos'], user['student_id'], date_str)
    homeworks = await parser.get_mosreg_homework(user['token_mos'], user['student_id'], date_str)
    
    response = f"📌 **Расписание на {date_str}:**\n"
    response += f"📋 Задано ЦДЗ: {len([h for h in homeworks if h['link']])}\n\n"
    
    if not schedule:
        response += "💨 Уроков не найдено."
    else:
        for item in schedule:
            dot = "🔴" if item['has_hw'] else "⚪"
            response += f"{dot} `{item['time']}` — **{item['subject']}**\n"
            hw_item = next((h for h in homeworks if h['subject'] == item['subject']), None)
            if hw_item:
                short_desc = hw_item['description'][:80] + "..." if len(hw_item['description']) > 80 else hw_item['description']
                response += f"   ┗ 📝 {short_desc}\n"

    await msg.edit_text(response, parse_mode="Markdown", reply_markup=get_hw_action_kb("all"))
    await state.set_state(BotStates.HOMEWORK_VIEW)

# Выбор дня -> Авто решение
@dp.callback_query(BotStates.AUTO_SOLVE_DAY, F.data.startswith("auto_"))
async def auto_day_select(call: types.CallbackQuery, state: FSMContext):
    date_str = call.data.replace("auto_", "")
    user = db.get_user(call.from_user.id)
    
    msg = await call.message.edit_text(f"🚀 **Авто-режим: Ищу ЦДЗ за {date_str}...**", parse_mode="Markdown")
    homeworks = await parser.get_mosreg_homework(user['token_mos'], user['student_id'], date_str)
    
    links = [h for h in homeworks if h['link']]
    if not links:
        await msg.edit_text("✅ Заданий с тестами на этот день не найдено!", reply_markup=get_main_menu_kb())
        await state.set_state(BotStates.MAIN_MENU)
        return

    resp = f"🎯 **Найдено {len(links)} теста(ов):**\n\n"
    builder = InlineKeyboardBuilder()
    for i, h in enumerate(links):
        resp += f"{i+1}. {h['subject']}\n"
        builder.button(text=f"▶️ {h['subject']}", callback_data=f"solve_fast_{i}")
    
    builder.button(text="🔥 Решить всё сразу", callback_data="solve_all_now")
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    builder.adjust(1)
    
    await msg.edit_text(resp, reply_markup=builder.as_markup())

# Решение теста (Быстро / Точно)
@dp.callback_query(F.data.startswith("solve_"))
async def handle_solve(call: types.CallbackQuery, state: FSMContext):
    mode = "fast" if "fast" in call.data else "precise"
    user = db.get_user(call.from_user.id)
    data = await state.get_data()
    date_str = data.get('selected_date', datetime.now().strftime('%Y-%m-%d'))
    
    # Получаем список всех ЦДЗ чтобы найти нужное
    homeworks = await parser.get_mosreg_homework(user['token_mos'], user['student_id'], date_str)
    links = [h for h in homeworks if h['link']]
    
    if not links:
        await call.answer("❌ Тесты не найдены!")
        return

    # Находим индекс задачи если это не "solve_all_now"
    tasks_to_solve = []
    if "all_now" in call.data:
        tasks_to_solve = links
    elif "solve_fast_" in call.data:
        idx = int(call.data.replace("solve_fast_", ""))
        if idx < len(links): tasks_to_solve = [links[idx]]
    elif "solve_precise_" in call.data:
        # Для ручного режима из 'Моё ДЗ'
        subject = call.data.replace("solve_precise_", "")
        if subject == "all": tasks_to_solve = links
        else: tasks_to_solve = [l for l in links if l['subject'] == subject]
    
    if not tasks_to_solve:
        await call.answer("❌ Задание не найдено!")
        return

    await call.message.edit_text("⚙️ **Инициализация решателя...**", parse_mode="Markdown")
    
    for task in tasks_to_solve:
        await call.message.answer(f"🧩 **Начинаю: {task['subject']}**")
        
        async def status_update(text):
            try: await call.message.answer(f"ℹ️ {text}")
            except: pass
            
        async def send_screen(path):
            await call.message.answer_photo(photo=types.FSInputFile(path), caption="📸 Скриншот процесса")

        result = await parser._solve_mesh(user, task['link'], status_update, send_screen)
        await call.message.answer(f"🏁 **{task['subject']}:** {result}", parse_mode="Markdown")
    
    await call.message.answer("🎉 **Готово!** Все доступные задания обработаны.", reply_markup=get_main_menu_kb())
    await state.set_state(BotStates.MAIN_MENU)

# Настройки -> Очистка кеша
@dp.callback_query(BotStates.SETTINGS, F.data == "set_clear_cache")
async def clear_cache(call: types.CallbackQuery):
    # В реальности тут удаление из БД
    await call.answer("🧹 Кеш очищен!", show_alert=True)

# Навигация назад к неделям
@dp.callback_query(F.data.startswith("back_to_weeks_"))
async def back_to_weeks(call: types.CallbackQuery, state: FSMContext):
    prefix = call.data.replace("back_to_weeks_", "")
    await state.set_state(BotStates.WEEK_SELECTION if prefix == "manual" else BotStates.AUTO_SOLVE_WEEK)
    await call.message.edit_text("📅 **Выберите неделю:**", reply_markup=get_week_kb(prefix=prefix), parse_mode="Markdown")

# ─── НАСТРОЙКИ И ПРОФИЛЬ ───

@dp.callback_query(BotStates.SETTINGS, F.data == "set_profile")
async def view_profile(call: types.CallbackQuery):
    user = db.get_user(call.from_user.id)
    stats = db.get_stats(call.from_user.id)
    
    profile_text = (
        f"👤 **Профиль пользователя**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📛 Имя: {user.get('first_name') or 'Не указано'}\n"
        f"🏫 Класс: {user.get('grade') or 'Не указан'}\n"
        f"🔑 Статус: {'✅ Подключен' if user.get('token_mos') else '❌ Не привязан'}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 **Статистика:**\n"
        f"✅ Решено ДЗ: {stats['solved']}\n"
        f"⭐ Средний балл: {stats['avg']}\n"
        f"💎 Сэкономлено: {stats['saved']} токенов\n"
    )
    await call.message.edit_text(profile_text, parse_mode="Markdown", reply_markup=get_settings_kb())

# ─── ПРИЕМ ТОКЕНА ───

@dp.message(F.text.startswith("eyJ"))
async def process_token(message: types.Message, state: FSMContext):
    token = message.text.strip()
    await message.answer("🔍 **Проверка токена...**")
    
    profile = await parser.fetch_mosreg_profile(token)
    if profile:
        db.update_user(message.from_user.id, 
                       token_mos=token, 
                       first_name=profile['first_name'], 
                       last_name=profile['last_name'],
                       grade=profile.get('grade', ''),
                       student_id=profile['student_id'])
        
        await message.answer(
            f"✅ **Успешно!**\nПривет, {profile['first_name']}! Аккаунт привязан.\n"
            "Теперь ты можешь просматривать ЦДЗ и пользоваться авто-решением.",
            reply_markup=get_main_menu_kb()
        )
        await state.set_state(BotStates.MAIN_MENU)
    else:
        await message.answer("❌ **Ошибка!** Токен не подходит или истек. Перезайди в Школьный Портал и скопируй новый.")

# ─── ЧТО ТАКОЕ ТОКЕН ───

@dp.callback_query(F.data == "what_is_token")
async def explain_token(call: types.CallbackQuery):
    explain_text = (
        "🔑 **Токен — это твой цифровой ключ!**\n\n"
        "Он нужен, чтобы бот смог безопасно подключиться к твоему учебному аккаунту "
        "(как логин/пароль, но без риска).\n\n"
        "✨ **Как работает?**\n"
        "1️⃣ Токен даёт доступ **только к тестам** — не трогает другие данные.\n"
        "2️⃣ Действует **ограниченное время**, не нужно лишний раз менять пароль.\n"
        "3️⃣ Гарантирует безопасность твоих личных данных.\n\n"
        "⚠️ **Без него бот не решит ни одного задания!**\n"
        "Это единственный способ авторизации без передачи вашего пароля сторонним лицам."
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Вернуться в главное меню", callback_data="back_to_main")
    await call.message.edit_text(explain_text, parse_mode="Markdown", reply_markup=builder.as_markup())

# ─── НАСТРОЙКИ: ОБНОВИТЬ ДАННЫЕ ───

@dp.callback_query(F.data == "refresh_data")
async def refresh_user_data(call: types.CallbackQuery, state: FSMContext):
    user = db.get_user(call.from_user.id)
    if not user.get('token_mos'):
        await call.answer("⚠️ Сначала привяжите токен!", show_alert=True)
        return
    
    await call.message.edit_text("🔄 **Обновляю данные из системы...**", parse_mode="Markdown")
    
    try:
        profile = await parser.get_mosreg_profile(user['token_mos'])
        if profile:
            db.update_user(call.from_user.id, grade=profile['grade'], student_id=profile['student_id'])
            await call.message.edit_text("✅ **Данные успешно обновлены!**", reply_markup=get_settings_kb(), parse_mode="Markdown")
        else:
            await call.message.edit_text("❌ **Ошибка обновления.** Попробуйте позже.", reply_markup=get_settings_kb(), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error refreshing data: {e}")
        await call.message.edit_text("❌ **Техническая ошибка.** Проверьте токен.", reply_markup=get_settings_kb(), parse_mode="Markdown")

# ─── НАСТРОЙКИ: ПОДПИСКА ───

@dp.callback_query(F.data == "subscription_info")
async def subscription_info(call: types.CallbackQuery):
    await call.answer()
    sub_text = (
        "💳 **Информация о подписке**\n\n"
        "Подписка открывает доступ к:\n"
        "🚀 Мгновенному решению без очередей\n"
        "📂 Архиву всех решенных работ\n"
        "👤 Личному менеджеру поддержки\n\n"
        "💎 **Стоимость: 299₽ / месяц**\n\n"
        "Чтобы оформить, пишите администратору: @admin_username"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад к настройкам", callback_data="back_to_settings")
    await call.message.edit_text(sub_text, parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "back_to_settings")
async def back_to_settings(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    user = db.get_user(call.from_user.id)
    await call.message.edit_text(
        "⚙️ **Настройки бота:**",
        reply_markup=get_settings_kb(user.get('solve_delay', 15), user.get('accuracy_mode', 'excellent')),
        parse_mode="Markdown"
    )

# ─── НАСТРОЙКИ: СКОРОСТЬ И ТОЧНОСТЬ ───

@dp.callback_query(F.data == "set_speed_menu")
async def speed_menu(call: types.CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        "⏱ **Настройка скорости решения**\n\n"
        "Выберите время задержки перед отправкой ответов. "
        "Это помогает имитировать поведение человека.\n\n"
        "По умолчанию: **15 минут**",
        reply_markup=get_speed_kb(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("save_speed_"))
async def save_speed(call: types.CallbackQuery):
    await call.answer()
    speed = int(call.data.replace("save_speed_", ""))
    db.update_user(call.from_user.id, solve_delay=speed)
    user = db.get_user(call.from_user.id)
    await call.message.edit_text(
        "⚙️ **Настройки бота:**",
        reply_markup=get_settings_kb(user.get('solve_delay'), user.get('accuracy_mode')),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "set_accuracy_menu")
async def accuracy_menu(call: types.CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        "🎯 **Выбор режима точности**\n\n"
        "Выберите желаемый процент правильных ответов для ваших тестов:",
        reply_markup=get_accuracy_kb(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("save_acc_"))
async def save_accuracy(call: types.CallbackQuery):
    await call.answer()
    mode = call.data.replace("save_acc_", "")
    db.update_user(call.from_user.id, accuracy_mode=mode)
    user = db.get_user(call.from_user.id)
    await call.message.edit_text(
        "⚙️ **Настройки бота:**",
        reply_markup=get_settings_kb(user.get('solve_delay'), user.get('accuracy_mode')),
        parse_mode="Markdown"
    )

# Обработчик завершен (дубликат удален выше)

# ─── ЗАПУСК ───

async def main():
    logger.info("Bot started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
