from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
import logging

from database.db import Database
from services.parser import ParserService
from keyboards.inline import get_profile_kb
from keyboards.reply import get_main_menu_kb

router = Router()
db = Database()
parser = ParserService()
logger = logging.getLogger(__name__)

async def get_student_info(user_id):
    user = await db.get_user(user_id)
    stats = await db.get_stats(user_id)
    
    text = (
        f"👤 <b>ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        f"📝 Имя: {user.get('first_name', 'Не указано')} {user.get('last_name', '')}\n"
        f"🏫 Класс: {user.get('grade', 'Не определен')}\n"
        f"🆔 ID: <code>{user.get('student_id', '---')}</code>\n\n"
        f"📊 <b>СТАТИСТИКА</b>\n"
        f"✅ Решено тестов: {stats['solved']}\n"
        f"📈 Ср. результат: {stats['avg']}%\n"
        f"👁️ Отправлено ответов: {stats['saved']} (активаций)\n\n"
        f"📅 Подписка: <b>Базовая (Бесплатно)</b>"
    )
    return text

@router.message(F.text == "👤 ПРОФИЛЬ")
async def show_profile(message: types.Message):
    text = await get_student_info(message.from_user.id)
    # Возвращаем стандартное меню, если зашли из расписания
    await message.answer(text, reply_markup=get_main_menu_kb(), parse_mode="HTML")
    await message.answer("👆 Управление профилем:", reply_markup=get_profile_kb(), parse_mode="HTML")

@router.callback_query(F.data == "refresh_profile_data")
async def refresh_profile_cb(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    try:
        new_info = await parser.fetch_mosreg_profile(user['token_mos'])
        await db.update_user(
            callback.from_user.id, 
            first_name=new_info['first_name'],
            last_name=new_info['last_name'],
            grade=new_info['grade'],
            student_id=new_info['student_id'],
            mesh_id=new_info.get('mesh_id')
        )
        await callback.answer("✅ Данные обновлены")
        await show_profile(callback.message)
        await callback.message.delete()
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)[:40]}")

@router.callback_query(F.data == "delete_token_confirm")
async def delete_token_cb(callback: types.CallbackQuery):
    await db.update_user(callback.from_user.id, token_mos=None)
    await callback.message.edit_text("🗑 Токен удален. Бот сброшен.\nВведите /start для новой авторизации.")
    await callback.answer()
