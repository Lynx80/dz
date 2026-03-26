import asyncio
import logging
import os
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest
from aiogram.client.session.aiohttp import AiohttpSession

from database import Database
from parser import ParserService, MosregAuthError

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
    WAITING_FOR_TOKEN = State()

# ─── КЛАВИАТУРЫ ───

def get_main_menu_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📚 МОЁ ДЗ")
    builder.button(text="⚡ АВТО РЕШЕНИЕ")
    builder.button(text="👤 ПРОФИЛЬ")
    builder.button(text="⚙️ НАСТРОЙКИ")
    builder.button(text="📡 О НАС")
    builder.button(text="💬 ПОДДЕРЖКА")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_week_kb(prefix="week"):
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 ПРЕДЫДУЩАЯ", callback_data=f"{prefix}_prev")
    builder.button(text="📅 ТЕКУЩАЯ", callback_data=f"{prefix}_curr")
    builder.button(text="🔙 НАЗАД", callback_data="back_to_main")
    builder.adjust(2, 1)
    return builder.as_markup()

def get_days_kb(week_offset=0, prefix="day"):
    builder = InlineKeyboardBuilder()
    today = datetime.now()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    days_ru = ["ПН", "ВТ", "СР", "ЧТ", "ПТ"]
    for i in range(5):
        d = monday + timedelta(days=i)
        date_str = d.strftime('%Y-%m-%d')
        builder.button(text=f"{days_ru[i]} {d.strftime('%d.%m')}", callback_data=f"{prefix}_{date_str}")
    builder.button(text="🔙 НАЗАД", callback_data=f"back_to_weeks_{prefix}")
    builder.adjust(3, 2, 1)
    return builder.as_markup()

def get_hw_action_kb(date_str, prefix="manual"):
    builder = InlineKeyboardBuilder()
    builder.button(text="🎯 РЕШАТЬ ВСЕ ЦДЗ ЗА СЕГОДНЯ", callback_data=f"batch_solve_pre_{date_str}")
    builder.button(text="🔍 РЕШАТЬ ВЫБОРОЧНО", callback_data=f"selective_solve_{date_str}")
    builder.button(text="🔄 ОБНОВИТЬ", callback_data=f"refresh_day_{date_str}_{prefix}")
    builder.button(text="🔙 НАЗАД", callback_data="back_to_days")
    builder.adjust(1, 1, 2)
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

async def check_token(message: types.Message, user):
    if not user or not user.get('token_mos'):
        help_text = (
            "⚠️ ТОКЕН НЕ ЗАГРУЖЕН!\n\n"
            "Токен — это твой цифровой ключ! Он дает боту доступ к тестам! 🔑\n\n"
            "Как получить токен:\n\n"
            "1️⃣ Перейди по ссылке:\n"
            "- [Москва](https://school.mos.ru/?backUrl=https%3A%2F%2Fschool.mos.ru%2Fv2%2Ftoken%2Frefresh)\n"
            "- Для Московской области:\n"
            "  • [Войти в аккаунт](https://authedu.mosreg.ru/50/)\n"
            "  • [Получить токен](https://authedu.mosreg.ru/v2/token/refresh)\n\n"
            "2️⃣ Введи логин и пароль от своего аккаунта.\n"
            "(Не волнуйся, мы их не видим — это только для системы! 🔒)\n\n"
            "3️⃣ Скопируй токен с открывшейся страницы.\n"
            "(Он начинается с 'eyJhbG...')\n\n"
            "4️⃣ Отправь токен сюда, и наш бот сразу приступит к работе! 🚀\n\n"
            "P.S. Без токена — никаких тестов. Так что действуй! 🔥\n"
            "Для МО обязательно сначала войти в аккаунт, а потом получить токен!"
        )
        if isinstance(message, types.CallbackQuery):
            await message.message.answer(help_text, reply_markup=get_token_help_kb(), disable_web_page_preview=True, parse_mode="Markdown")
        else:
            await message.answer(help_text, reply_markup=get_token_help_kb(), disable_web_page_preview=True, parse_mode="Markdown")
        return False
    return True

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
    await message.answer("📅 ВЫБЕРИТЕ НЕДЕЛЮ:", reply_markup=get_week_kb(prefix="manual"))
    await state.set_state(BotStates.WEEK_SELECTION)

@dp.message(F.text == "⚡ АВТО РЕШЕНИЕ")
async def auto_solve_start(message: types.Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    if not await check_token(message, user): return
    await message.answer("🚀 АВТО-РЕЖИМ: ВЫБЕРИТЕ НЕДЕЛЮ:", reply_markup=get_week_kb(prefix="auto"))
    await state.set_state(BotStates.AUTO_SOLVE_WEEK)

@dp.message(F.text == "👤 ПРОФИЛЬ")
async def profile_main(message: types.Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    stats = db.get_stats(message.from_user.id)
    text = (
        f"👤 ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ\n━━━━━━━━━━━━━━━\n"
        f"📛 ИМЯ: {user.get('first_name') or 'НЕ УКАЗАНО'}\n"
        f"🏫 КЛАСС: {user.get('grade') or 'НЕ УКАЗАН'}\n"
        f"🔑 СТАТУС: {'✅ ПОДКЛЮЧЕН' if user.get('token_mos') else '❌ НЕ ПРИВЯЗАН'}\n"
        f"━━━━━━━━━━━━━━━\n📊 СТАТИСТИКА:\n"
        f"✅ РЕШЕНО ДЗ: {stats['solved']}\n"
        f"⭐ СРЕДНИЙ БАЛЛ: {stats['avg']}\n"
        f"💎 СЭКОНОМЛЕНО: {stats['saved']} ТОКЕНОВ\n"
    )
    await message.answer(text, reply_markup=get_profile_kb())

@dp.message(F.text == "⚙️ НАСТРОЙКИ")
async def settings_start(message: types.Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    await message.answer("⚙️ НАСТРОЙКИ БОТА:\n\nЗДЕСЬ МОЖНО НАСТРОИТЬ СКОРОСТЬ И ТОЧНОСТЬ.", 
                         reply_markup=get_settings_kb(user.get('solve_delay', 15), user.get('accuracy_mode', 'excellent')))
    await state.set_state(BotStates.SETTINGS)

@dp.message(F.text == "📡 О НАС")
async def about_main(message: types.Message, state: FSMContext):
    await message.answer("📡 О ПРОЕКТЕ\n\nЭТОТ БОТ ОРГАНИЗОВАН ДЛЯ ПОМОЩИ УЧЕНИКАМ В АВТОМАТИЗАЦИИ ЦДЗ.\n\n📢 КАНАЛ: @your_channel")

@dp.message(F.text == "💬 ПОДДЕРЖКА")
async def support_main(message: types.Message, state: FSMContext):
    await message.answer("💬 ЧАТ ПОДДЕРЖКИ\n\n🔗 ССЫЛКА: [ПЕРЕЙТИ В ЧАТ](https://t.me/your_support_chat)", parse_mode="Markdown")

# ─── CALLBACKS ───

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.MAIN_MENU)
    try: await call.message.edit_text("🏠 ГЛАВНОЕ МЕНЮ:", reply_markup=get_main_menu_kb())
    except: await call.message.answer("🏠 ГЛАВНОЕ МЕНЮ:", reply_markup=get_main_menu_kb())

@dp.callback_query(F.data.startswith("back_to_weeks_"))
async def back_to_weeks(call: types.CallbackQuery, state: FSMContext):
    prefix = call.data.replace("back_to_weeks_", "")
    await state.set_state(BotStates.WEEK_SELECTION if "manual" in prefix else BotStates.AUTO_SOLVE_WEEK)
    await call.message.edit_text("📅 ВЫБЕРИТЕ НЕДЕЛЮ:", reply_markup=get_week_kb(prefix=prefix))

@dp.callback_query(F.data == "back_to_days")
async def back_to_days_handler(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await call.message.edit_text("📅 ВЫБЕРИТЕ ДЕНЬ:", reply_markup=get_days_kb(data.get('week_offset', 0), prefix="manual"))

@dp.callback_query(StateFilter(BotStates.WEEK_SELECTION, BotStates.AUTO_SOLVE_WEEK), F.data.contains("_prev") | F.data.contains("_curr"))
async def week_select(call: types.CallbackQuery, state: FSMContext):
    prefix = "manual" if "manual" in call.data else "auto"
    offset = 0 if "curr" in call.data else -1
    await state.update_data(week_offset=offset)
    await state.set_state(BotStates.DAY_SELECTION if prefix == "manual" else BotStates.AUTO_SOLVE_DAY)
    await call.message.edit_text("📅 ВЫБЕРИТЕ ДЕНЬ:", reply_markup=get_days_kb(offset, prefix=prefix))

@dp.callback_query(F.data.startswith("manual_"))
@dp.callback_query(F.data.startswith("refresh_day_"))
async def manual_day_select(call: types.CallbackQuery, state: FSMContext):
    if "refresh" in call.data:
        parts = call.data.split("_")
        date_str = parts[2]
    else:
        date_str = call.data.split("_")[1]
        
    await state.update_data(selected_date=date_str)
    user = db.get_user(call.from_user.id)
    
    # 1. Получаем данные
    try:
        schedule = await parser.get_mosreg_schedule(user['token_mos'], user['student_id'], date_str)
        homeworks = await parser.get_mosreg_homework(user['token_mos'], user['student_id'], date_str)
    except MosregAuthError:
        await call.message.edit_text(
            "⚠️ ВАША СЕССИЯ ИСТЕКЛА!\n\nТОКЕН БОЛЬШЕ НЕ ДЕЙСТВИТЕЛЕН. ПОЖАЛУЙСТА, ОБНОВИТЕ ЕГО:\n"
            "🔗 [ПОЛУЧИТЬ НОВЫЙ ТОКЕН](https://authedu.mosreg.ru/v2/token/refresh)\n\n"
            "ПРОСТО ОТПРАВЬТЕ НОВЫЙ ТОКЕН МНЕ.",
            reply_markup=InlineKeyboardBuilder().button(text="🔙 В МЕНЮ", callback_data="back_to_main").as_markup(),
            parse_mode="Markdown"
        )
        return
    
    text = f"📍 РАСПИСАНИЕ НА {date_str}:\n🗓️ ЗАДАНО ЦДЗ: {len(homeworks)}\n━━━━━━━━━━━━━━━\n\n"
    
    if not schedule:
        text += "💨 УРОКОВ НЕ НАЙДЕНО."
    else:
        for i, item in enumerate(schedule, 1):
            room = f"КАБ. № {item['room']}" if item['room'] else "КАБ. НЕ УКАЗАН"
            text += f"{i} УРОК {item['time']} {room}\n"
            text += f"{item['subject'].upper()}\n"
            
            # Ищем домашку для этого предмета
            hw_item = next((h for h in homeworks if h['subject'].lower() in item['subject'].lower() or item['subject'].lower() in h['subject'].lower()), None)
            if hw_item:
                text += "📝 ДОМАШНЕЕ ЗАДАНИЕ (ЦДЗ):\n"
                desc = hw_item['description'][:100] + "..." if len(hw_item['description']) > 100 else hw_item['description']
                text += f"   ┗ {desc.upper()}\n"
            else:
                text += "📝 ДОМАШНЕЕ ЗАДАНИЕ:\n"
                text += "   ┗ БЕЗ Д/З\n"
            text += "━━━━━━━━━━━━━━━\n"
    
    await call.message.edit_text(text, reply_markup=get_hw_action_kb(date_str))

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
        homeworks = await parser.get_mosreg_homework(user['token_mos'], user['student_id'], date_str)
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
    profile = await parser.get_mosreg_profile(user['token_mos'])
    if profile:
        db.update_user(call.from_user.id, grade=profile['grade'], student_id=profile['student_id'])
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
        db.update_user(message.from_user.id, token_mos=token, first_name=profile['first_name'], grade=profile.get('grade', ''), student_id=profile['student_id'])
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

async def token_refresher_task():
    """Фоновая задача для автоматического обновления токенов каждые 40 минут."""
    while True:
        try:
            logger.info("Starting background token refresh cycle...")
            users = db.get_all_users_with_tokens()
            for u in users:
                try:
                    new_token = await parser.refresh_token(u['token_mos'])
                    if new_token:
                        db.update_user(u['user_id'], token_mos=new_token)
                        logger.info(f"Refreshed token for user {u['user_id']}")
                    else:
                        logger.warning(f"Could not refresh token for user {u['user_id']} (no response)")
                except MosregAuthError:
                    logger.warning(f"Token for user {u['user_id']} is dead. Stopping refresher for this user.")
                    # Опционально: db.update_user(u['user_id'], token_mos=None) 
                    # Но лучше оставить как есть, чтобы bot.py показал ошибку в UI
                
                # Небольшая пауза между пользователями
                await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Refresher task error: {e}")
        
        await asyncio.sleep(40 * 60)

async def main():
    logger.info("Bot started!")
    # Запуск фоновой задачи
    asyncio.create_task(token_refresher_task())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
