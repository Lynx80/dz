from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.db_service import save_user_token, update_user_profile
from services.school_api import SchoolAPI

router = Router()

class AuthStates(StatesGroup):
    waiting_token = State()

@router.message(F.text == "⚙️ Настройки")
async def settings_menu(message: types.Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="🏙 Москва: Получить токен", 
        url="https://school.mos.ru/?backUrl=https%3A%2F%2Fschool.mos.ru%2Fv2%2Ftoken%2Frefresh"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🌍 МО: 1. Войти", 
        url="https://authedu.mosreg.ru/"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🌍 МО: 2. Получить токен", 
        url="https://authedu.mosreg.ru/v2/token/refresh"
    ))
    
    await message.answer(
        "🛠 **Настройки авторизации**\n\n"
        "1. Войди на портал по кнопкам ниже.\n"
        "2. Скопируй полученный токен (начинается с `eyJ...`).\n"
        "3. Просто отправь его мне в чат!",
        reply_markup=builder.as_markup()
    )
    await state.set_state(AuthStates.waiting_token)

@router.message(F.text.startswith("eyJ"))
async def handle_token_input(message: types.Message, state: FSMContext):
    token = message.text.strip()
    await save_user_token(message.from_user.id, token)
    
    msg = await message.answer("🔄 Проверяю токен и загружаю ваш профиль...")
    
    # Пытаемся получить профиль сразу
    api = SchoolAPI(token)
    profile = await api.get_profile()
    
    if profile:
        await update_user_profile(
            message.from_user.id, 
            profile["first_name"], 
            profile["last_name"], 
            profile["class_name"]
        )
        await msg.edit_text(
            f"✅ Авторизация успешна!\n\n"
            f"👤 **Ученик**: {profile['last_name']} {profile['first_name']}\n"
            f"🏫 **Класс**: {profile['class_name']}"
        )
    else:
        await msg.edit_text("⚠️ Токен сохранен, но не удалось загрузить данные профиля. "
                           "Возможно, нужно подождать или попробовать другой регион.")
    
    await state.clear()
