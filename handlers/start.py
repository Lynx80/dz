from aiogram import Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from database.db_service import get_user_token

router = Router()

def get_main_menu_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="🤖 Авторешение")
    builder.button(text="👤 Профиль")
    builder.button(text="💻 Мои ЦДЗ тесты")
    builder.button(text="🔄 Обновить данные")
    builder.button(text="⚙️ Настройки")
    builder.adjust(1, 2, 2)
    return builder.as_markup(resize_keyboard=True)

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    token = await get_user_token(message.from_user.id)
    if not token:
        await message.answer(
            "👋 Привет! Я твой помощник по ЦДЗ.\n\n"
            "🔑 Для начала работы мне нужен твой токен из школьного портала.\n"
            "Нажми '⚙️ Настройки' или отправь токен прямо сейчас!",
            reply_markup=get_main_menu_kb()
        )
    else:
        await message.answer(
            "👋 С возвращением! Выбери действие в меню:",
            reply_markup=get_main_menu_kb()
        )
