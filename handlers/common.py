from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime

from database.db import Database
from keyboards.reply import get_main_menu_kb
from keyboards.inline import get_token_help_kb
from utils.states import BotStates

router = Router()
db = Database()

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = await db.get_user(message.from_user.id)
    
    if not user or not user.get('token_mos'):
        text = (
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            "Я — твой помощник по МЭШ и Мосрег. Я могу:\n"
            "📚 Показывать актуальное ДЗ\n"
            "🧠 Решать ЦДЗ тесты (МЭШ, Videouroki)\n"
            "📈 Вести статистику твоих оценок\n\n"
            "⚠️ Чтобы начать, мне нужен твой **Access Token**."
        )
        await message.answer(text, reply_markup=get_token_help_kb(), parse_mode="Markdown")
        await state.set_state(BotStates.waiting_for_token)
    else:
        text = f"👋 С возвращением, {user.get('first_name', message.from_user.first_name)}!"
        await message.answer(text, reply_markup=get_main_menu_kb())

@router.message(F.text == "🏠 МЕНЮ")
@router.message(Command("menu"))
async def show_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_main_menu_kb())

from services.parser import ParserService, MosregAuthError

parser = ParserService()

@router.message(BotStates.waiting_for_token)
async def process_token_input(message: types.Message, state: FSMContext):
    token = message.text.strip().strip('"')
    if not token.startswith("eyJ"):
        await message.answer("❌ Это не похоже на правильный токен. Он должен начинаться с 'eyJ...'. Попробуйте еще раз.")
        return
        
    wait_msg = await message.answer("🔍 Проверяю токен и получаю данные профиля...")
    
    try:
        user_info = await parser.fetch_mosreg_profile(token)
        # Сохраняем/обновляем пользователя
        await db.create_user(
            message.from_user.id,
            first_name=user_info.get('first_name'),
            last_name=user_info.get('last_name'),
            grade=user_info.get('grade'),
            student_id=user_info.get('student_id'),
            mesh_id=user_info.get('mesh_id')
        )
        await db.update_user(message.from_user.id, token_mos=token)
        
        await wait_msg.edit_text(
            f"✅ Авторизация успешна!\n"
            f"👤 Имя: {user_info['first_name']} {user_info['last_name']}\n"
            f"🏫 Класс: {user_info['grade']}\n\n"
            "Теперь вы можете смотреть ДЗ и решать тесты!"
        )
        await message.answer("Воспользуйтесь меню:", reply_markup=get_main_menu_kb())
        await state.clear()
        
    except MosregAuthError:
        await wait_msg.edit_text("❌ Ошибка: Токен недействителен или истек. Получите новый токен и попробуйте снова.")
    except Exception as e:
        logger.error(f"Auth error: {e}")
        await wait_msg.edit_text(f"❌ Произошла ошибка при авторизации: {str(e)[:50]}")
