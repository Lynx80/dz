from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
import logging

from database.db import Database
from services.parser import ParserService, MosregAuthError
from keyboards.inline import get_settings_kb, get_speed_kb, get_accuracy_kb
from keyboards.reply import get_main_menu_kb

router = Router()
db = Database()
parser = ParserService()
logger = logging.getLogger(__name__)

@router.message(F.text == "⚙️ НАСТРОЙКИ")
async def show_settings(message: types.Message):
    user = await db.get_user(message.from_user.id)
    await message.answer(
        "⚙️ Настройки бота:\n\n"
        "⏱️ Скорость — задержка между вопросами\n"
        "🎯 Точность — шанс выбора правильного ответа AI\n"
        "🔄 Обновить — очистка кеша и данных профиля",
        reply_markup=get_main_menu_kb(), # Сбрасываем контекстное меню
    )
    # Отправляем инлайн настройки отдельно
    await message.answer(
        "🔧 Выберите параметр для изменения:",
        reply_markup=get_settings_kb(
            solve_delay=user.get('solve_delay', 15), 
            accuracy_mode=user.get('accuracy_mode', 'advanced')
        )
    )

@router.callback_query(F.data == "set_speed_menu")
async def speed_menu_cb(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    await callback.message.edit_text("Выберите время решения (мин):", reply_markup=get_speed_kb(user.get('solve_delay', 15)))
    await callback.answer()

@router.callback_query(F.data.startswith("save_speed_"))
async def save_speed_cb(callback: types.CallbackQuery):
    speed = int(callback.data.split("_")[-1])
    await db.update_user(callback.from_user.id, solve_delay=speed)
    await callback.answer(f"✅ Установлено: {speed} мин")
    await show_settings(callback.message)
    await callback.message.delete()

@router.callback_query(F.data == "set_accuracy_menu")
async def acc_menu_cb(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    await callback.message.edit_text("Выберите точность AI:", reply_markup=get_accuracy_kb(user.get('accuracy_mode', 'advanced')))
    await callback.answer()

@router.callback_query(F.data.startswith("save_acc_"))
async def save_acc_cb(callback: types.CallbackQuery):
    acc = callback.data.split("_")[-1]
    await db.update_user(callback.from_user.id, accuracy_mode=acc)
    await callback.answer(f"✅ Точность обновлена")
    await show_settings(callback.message)
    await callback.message.delete()

@router.callback_query(F.data == "back_to_settings")
async def back_to_settings_cb(callback: types.CallbackQuery):
    await show_settings(callback.message)
    await callback.message.delete()
    await callback.answer()
