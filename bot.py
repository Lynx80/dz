import asyncio
import logging
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.client.session.aiohttp import AiohttpSession

from database import Database
from parser import ParserService

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dp = Dispatcher(storage=MemoryStorage())
db = Database()
parser = ParserService()

# ─── КЛАВИАТУРЫ ───

def get_main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="👤 Мой профиль")
    builder.button(text="📚 Список ЦДЗ")
    builder.button(text="📖 Решить тест")
    builder.button(text="❓ Как войти")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_profile_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Обновить данные", callback_data="sync_profile")
    builder.button(text="🗑️ Сбросить токен", callback_data="reset_token")
    builder.adjust(1)
    return builder.as_markup()

def get_region_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🏙️ Москва (МЭШ)", callback_data="region_mos")
    builder.button(text="🌲 Область (Мосрег)", callback_data="region_mo")
    builder.adjust(1)
    return builder.as_markup()

def get_hw_kb():
    """Динамические даты для выбора ЦДЗ."""
    today = datetime.now()
    tomorrow = today + timedelta(days=1)
    
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"📅 Сегодня ({today.strftime('%d.%m')})",
        callback_data=f"hw_date_{today.strftime('%Y-%m-%d')}"
    )
    builder.button(
        text=f"📅 Завтра ({tomorrow.strftime('%d.%m')})",
        callback_data=f"hw_date_{tomorrow.strftime('%Y-%m-%d')}"
    )
    builder.adjust(1)
    return builder.as_markup()

# ─── КОМАНДЫ ───

@dp.message(Command("start"))
async def send_welcome(message: types.Message, state: FSMContext):
    await state.clear()
    user = db.get_user(message.from_user.id)
    if not user:
        db.create_user(message.from_user.id, first_name="Друг")
    
    await message.answer(
        "Привет! 👋 Я твой помощник по школьным тестам.\n"
        "Помогу найти и решить задания из ЦДЗ.",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )
    
    updated_user = db.get_user(message.from_user.id)
    if not updated_user or not (updated_user.get('token_mo') or updated_user.get('token_mos')):
        await message.answer(
            "⚠️ **Токен не найден**\nДля начала работы подключите ваш аккаунт:",
            reply_markup=get_region_kb()
        )

@dp.message(Command("restart"))
async def full_restart(message: types.Message, state: FSMContext):
    db.delete_user(message.from_user.id)
    await state.clear()
    await message.answer("♻️ **Все данные сброшены!**")
    await send_welcome(message, state)

# ─── КАК ВОЙТИ ───

@dp.message(F.text == "❓ Как войти")
async def help_command(message: types.Message):
    await message.answer("📍 **Выберите ваш регион:**", reply_markup=get_region_kb())

@dp.callback_query(F.data == "region_mo")
async def step1_mo(callback: types.CallbackQuery):
    text = (
        "🌲 **ШАГ 1: Вход в Мосрег**\n\n"
        "Авторизуйтесь в системе «Моя Школа» через кнопку ниже."
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🌐 1. Войти в дневник", url="https://authedu.mosreg.ru/")
    kb.button(text="🔑 2. Я вошел, получить токен", callback_data="step2_mo")
    kb.button(text="🔙 Назад", callback_data="back_to_regions")
    kb.adjust(1)
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "step2_mo")
async def step2_mo(callback: types.CallbackQuery):
    text = (
        "🌲 **ШАГ 2: Получение токена**\n\n"
        "1. Нажмите кнопку ниже — откроется страница с токеном.\n"
        "2. Скопируйте длинный код (начинается на `eyJ...`).\n"
        "3. Пришлите его мне сообщением.\n\n"
        "⚠️ Если страница не открывается или выдаёт ошибку — "
        "вернитесь к Шагу 1 и убедитесь, что вы вошли в дневник."
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🔑 Получить токен", url="https://authedu.mosreg.ru/v2/token/refresh")
    kb.button(text="🔙 Назад", callback_data="region_mo")
    kb.adjust(1)
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "region_mos")
async def step1_mos(callback: types.CallbackQuery):
    text = (
        "🏙️ **ШАГ 1: Вход в МЭШ**\n\n"
        "Авторизуйтесь в Московской Электронной Школе."
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🌐 1. Войти в МЭШ", url="https://school.mos.ru")
    kb.button(text="🔑 2. Я вошел, получить токен", callback_data="step2_mos")
    kb.button(text="🔙 Назад", callback_data="back_to_regions")
    kb.adjust(1)
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "step2_mos")
async def step2_mos(callback: types.CallbackQuery):
    text = (
        "🏙️ **ШАГ 2: Получение токена**\n\n"
        "В МЭШ токен можно найти через F12 → Local Storage сайта school.mos.ru.\n"
        "Скопируйте `auth_token` и пришлите его мне."
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="region_mos")
    kb.adjust(1)
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "back_to_regions")
async def back_to_regions(callback: types.CallbackQuery):
    await callback.message.edit_text("📍 **Выберите ваш регион:**", reply_markup=get_region_kb())

# ─── ПРОФИЛЬ ───

@dp.message(F.text == "👤 Мой профиль")
async def show_profile(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user:
        db.create_user(message.from_user.id, first_name="Друг")
        user = db.get_user(message.from_user.id)
    
    has_token = "✅ Привязан" if user.get('token_mo') or user.get('token_mos') else "❌ Не привязан"
    first_name = user.get('first_name') or "Друг"
    last_name = user.get('last_name') or ""

    text = (
        f"🙋 **Твой профиль**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 **Имя**: {first_name} {last_name}\n"
        f"🎓 **Класс**: {user.get('grade') or '—'}\n"
        f"🔑 **Аккаунт**: {has_token}\n"
        f"📊 **Решено**: {user.get('tests_solved', 0)}\n"
        f"⭐ **Ср. балл**: {user.get('avg_score', 0):.1f}%"
    )
    await message.answer(text, reply_markup=get_profile_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "sync_profile")
async def sync_profile(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    token = user.get('token_mo') or user.get('token_mos')
    if not token:
        await callback.answer("⚠️ Токен не найден!", show_alert=True)
        return
    
    await callback.message.edit_text("🔄 Обновляю данные...")
    profile = await parser.fetch_mosreg_profile(token)
    if not profile:
        profile = await parser.fetch_mesh_profile(token)
    
    if profile:
        db.update_user(callback.from_user.id, **profile)
        user = db.get_user(callback.from_user.id)
        text = (
            f"🙋 **Твой профиль**\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👤 **Имя**: {user.get('first_name')} {user.get('last_name', '')}\n"
            f"🎓 **Класс**: {user.get('grade') or '—'}\n"
            f"🔑 **Аккаунт**: ✅ Привязан\n"
            f"📊 **Решено**: {user.get('tests_solved', 0)}\n"
            f"⭐ **Ср. балл**: {user.get('avg_score', 0):.1f}%"
        )
        await callback.message.edit_text(text, reply_markup=get_profile_kb(), parse_mode="Markdown")
        await callback.answer("Обновлено!")
    else:
        await callback.message.edit_text("❌ Не удалось получить данные.", reply_markup=get_profile_kb())

@dp.callback_query(F.data == "reset_token")
async def reset_token_callback(callback: types.CallbackQuery):
    db.update_user(callback.from_user.id,
                   token_mo=None, token_mos=None, student_id=None,
                   first_name="Друг", last_name="", grade=None)
    text = (
        "🙋 **Твой профиль**\n"
        "━━━━━━━━━━━━━━━\n"
        "👤 **Имя**: Друг\n"
        "🎓 **Класс**: —\n"
        "🔑 **Аккаунт**: ❌ Не привязан\n"
        "📊 **Решено**: 0\n"
        "⭐ **Ср. балл**: 0.0%"
    )
    await callback.message.edit_text(text, reply_markup=get_profile_kb(), parse_mode="Markdown")
    await callback.answer("Токен сброшен!")

# ─── РЕШИТЬ / ЦДЗ ───

@dp.message(F.text == "📖 Решить тест")
async def solve_test_command(message: types.Message):
    user = db.get_user(message.from_user.id)
    token = user.get('token_mo') or user.get('token_mos') if user else None
    if not token:
        await message.answer(
            "⛔ **Доступ ограничен**\n"
            "Сначала привяжите аккаунт через раздел «❓ Как войти».",
            reply_markup=get_region_kb()
        )
        return
    await message.answer("Пришлите ссылку на тест (Videouroki или МЭШ), и я его решу! 🤖")

@dp.message(F.text == "📚 Список ЦДЗ")
async def homework_menu(message: types.Message):
    user = db.get_user(message.from_user.id)
    token = user.get('token_mo') or user.get('token_mos') if user else None
    if not token:
        await message.answer(
            "🛰️ **Токен не найден**\n"
            "Для просмотра ЦДЗ подключите аккаунт:",
            reply_markup=get_region_kb()
        )
        return
    await message.answer("📅 **Выберите день:**", reply_markup=get_hw_kb())

@dp.callback_query(F.data.startswith("hw_date_"))
async def show_hw_date(callback: types.CallbackQuery):
    date_str = callback.data.split("hw_date_")[1]
    user = db.get_user(callback.from_user.id)
    token = user.get('token_mo') or user.get('token_mos')
    student_id = user.get('student_id')
    
    status_msg = await callback.message.answer(f"🔍 Ищу задания на {date_str}...")
    hws = await parser.get_mosreg_homework(token, student_id, date_str=date_str)
    
    if not hws:
        await status_msg.edit_text(f"📭 На {date_str} заданий не найдено.")
    else:
        await status_msg.delete()
        for hw in hws:
            if hw.get('link'):
                text = f"📖 **{hw['subject']}**\n📅 {hw['date']}\n📝 {hw['description'] or ''}\n🔗 [Открыть]({hw['link']})"
            else:
                text = f"📖 **{hw['subject']}**\n📅 {hw['date']}\n📝 {hw['description'] or 'Без описания'}"
            await callback.message.answer(text, parse_mode="Markdown")

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await callback.message.delete()

# ─── ПРИЁМ ТОКЕНА ───

@dp.message(F.text.regexp(r'^eyJ[a-zA-Z0-9._\-]+$'))
async def process_token(message: types.Message):
    token = message.text.strip()
    status_msg = await message.answer("🔄 Проверяю токен...")
    
    # Токен уже готовый access_token — используем напрямую
    logger.info(f"Received token, length={len(token)}")
    
    # Пробуем получить профиль Мосрег
    profile = await parser.fetch_mosreg_profile(token)
    if profile:
        db.update_user(message.from_user.id, token_mo=token, **profile)
        name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
        sid = profile.get('student_id', '?')
        await status_msg.edit_text(
            f"✅ **Ура, {name}!**\n\n"
            f"Аккаунт привязан (ID: {sid}).\n"
            f"Теперь нажми «📚 Список ЦДЗ», чтобы увидеть задания!"
        )
        return
    
    # Пробуем МЭШ
    profile = await parser.fetch_mesh_profile(token)
    if profile:
        db.update_user(message.from_user.id, token_mos=token, **profile)
        name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
        await status_msg.edit_text(f"✅ **Ура, {name}!** Ты в МЭШ.")
        return
    
    # Ни один API не принял
    await status_msg.edit_text(
        "❌ **Токен не подходит.**\n\n"
        "Возможные причины:\n"
        "• Токен устарел или скопирован не полностью\n"
        "• Вы не авторизовались в дневнике перед получением токена\n\n"
        "Нажмите «❓ Как войти» и попробуйте снова."
    )

# ─── ССЫЛКИ НА ТЕСТЫ ───

@dp.message(F.text.startswith("https://"))
async def handle_link(message: types.Message):
    url = message.text.strip()
    status_msg = await message.answer("⌛ Начинаю решение...")
    async def update_status(text):
        try: await status_msg.edit_text(text)
        except: pass
    res = await parser.solve_test(message.from_user.id, url, update_status)
    await message.answer(res)

# ─── ЗАПУСК ───

async def main():
    API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or '8684063011:AAG5xtd4MfZLIc3FvGbXCABLnh-hcpieR_U'
    PROXY_URL = os.getenv("BROWSER_PROXY") or os.getenv("TELEGRAM_PROXY")
    
    async def try_start(token, proxy=None):
        session = AiohttpSession(proxy=proxy) if proxy else None
        bot = Bot(token=token, session=session)
        try:
            me = await bot.get_me()
            logger.info(f"Bot @{me.username} is online!")
            await dp.start_polling(bot)
            return True
        except Exception as e:
            logger.error(f"Connection error: {e}")
            if bot.session: await bot.session.close()
            return False

    if not await try_start(API_TOKEN, PROXY_URL):
        await try_start(API_TOKEN, None)

if __name__ == '__main__':
    asyncio.run(main())
