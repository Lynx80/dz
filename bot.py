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
    builder.button(text="📊 Статистика")
    builder.button(text="📡 О нас")
    builder.button(text="💳 Поддержка")
    builder.button(text="⚙️ Настройки")
    builder.adjust(2, 2, 2, 1)
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

def get_settings_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 Мой профиль", callback_data="set_profile")
    builder.button(text="⚙️ Режим: Быстрый", callback_data="set_mode_fast")
    builder.button(text="🧩 Очистить кеш", callback_data="set_clear_cache")
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

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
    await message.answer("📅 **Выберите неделю:**", reply_markup=get_week_kb(prefix="manual"))
    await state.set_state(BotStates.WEEK_SELECTION)

@dp.message(F.text == "⚡ Авто решение")
async def auto_solve_start(message: types.Message, state: FSMContext):
    await message.answer("🚀 **Авто-режим: Выберите неделю:**", reply_markup=get_week_kb(prefix="auto"))
    await state.set_state(BotStates.AUTO_SOLVE_WEEK)

@dp.message(F.text == "👤 Профиль")
async def profile_main(message: types.Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    profile_text = (
        f"👤 **Ваш профиль**\n\n"
        f"📛 Имя: {user.get('first_name') or 'Ученик'}\n"
        f"🏫 Класс: {user.get('grade') or 'Не указан'}\n"
        f"🔑 Статус: {'✅ Авторизован' if user.get('token_mos') else '❌ Нет токена'}"
    )
    await message.answer(profile_text, parse_mode="Markdown")

@dp.message(F.text == "📊 Статистика")
async def stats_main(message: types.Message, state: FSMContext):
    stats = db.get_stats(message.from_user.id)
    stats_text = (
        f"📊 **Ваша статистика**\n\n"
        f"✅ Решено тестов: {stats['solved']}\n"
        f"⭐ Средний балл: {stats['avg']}\n"
        f"💎 Сэкономлено: {stats['saved']} токенов"
    )
    await message.answer(stats_text, parse_mode="Markdown")

@dp.message(F.text == "📡 О нас")
async def about_main(message: types.Message, state: FSMContext):
    await message.answer(
        "📡 **О проекте**\n\n"
        "Этот бот создан для помощи ученикам в автоматизации ЦДЗ.\n"
        "Мы используем ИИ Gemini и Playwright для решения тестов.\n\n"
        "📢 Канал: @your_channel\n"
        "👥 Разработчик: @developer"
    )

@dp.message(F.text == "💳 Поддержка")
async def support_main(message: types.Message, state: FSMContext):
    await message.answer(
        "💳 **Поддержка проекта**\n\n"
        "Если бот помог тебе, ты можешь поддержать его развитие!\n"
        "Любая сумма поможет оплачивать прокси и API.\n\n"
        "🔗 Ссылка: [Поддержать](https://t.me/your_payment_link)",
        parse_mode="Markdown"
    )

@dp.message(F.text == "⚙️ Настройки")
async def settings_start(message: types.Message, state: FSMContext):
    await message.answer("⚙️ **Настройки бота:**", reply_markup=get_settings_kb())
    await state.set_state(BotStates.SETTINGS)

# ─── CALLBACK ХЕНДЛЕРЫ ───

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.MAIN_MENU)
    await call.message.edit_text("🏠 **Главное меню:**", reply_markup=get_main_menu_kb(), parse_mode="Markdown")

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

# ─── ЗАПУСК ───

async def main():
    logger.info("Bot started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
