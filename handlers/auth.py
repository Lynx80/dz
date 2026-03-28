from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.states import BotStates
from database.db import Database
from services.parser import ParserService, MosregAuthError
from keyboards.reply import get_main_menu_kb

router = Router()
db = Database()
parser = ParserService()

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
    await state.set_state(BotStates.waiting_for_token)

@router.message(F.text.startswith("eyJ"))
async def handle_token_input(message: types.Message, state: FSMContext):
    token = message.text.strip().strip('"')
    
    msg = await message.answer("🔄 Проверяю токен и загружаю ваш профиль...")
    
    try:
        user_info = await parser.fetch_mosreg_profile(token)
        # Сохраняем/обновляем пользователя в едином формате БД
        await db.create_user(
            message.from_user.id,
            first_name=user_info.get('first_name'),
            last_name=user_info.get('last_name'),
            grade=user_info.get('grade'),
            student_id=user_info.get('student_id'),
            mesh_id=user_info.get('mesh_id')
        )
        await db.update_user(message.from_user.id, token_mos=token)
        
        await msg.edit_text(
            f"✅ Авторизация успешна!\n\n"
            f"👤 **Ученик**: {user_info['last_name']} {user_info['first_name']}\n"
            f"🏫 **Класс**: {user_info['grade']}\n\n"
            "Теперь я вижу твое ДЗ и готов его решать! 🚀"
        )
        await message.answer("Воспользуйтесь меню ниже:", reply_markup=get_main_menu_kb())
        await state.clear()
        
    except MosregAuthError:
        await msg.edit_text("❌ Токен недействителен или истек. Получите новый токен и попробуйте снова.")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка авторизации: {str(e)[:100]}")
