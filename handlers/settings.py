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
    text = (
        "⚙️ <b>Настройки помощника</b>\n\n"
        "⏱️ <b>Время решения</b> — задержка между вопросами (имитация человека)\n"
        "🎯 <b>Точность AI</b> — шанс выбора правильного ответа\n"
        "🔄 <b>Обновить данные</b> — очистка локального кеша\n\n"
        "<i>Настройте бота под свои нужды:</i>"
    )
    await message.answer(
        text,
        reply_markup=get_settings_kb(
            solve_delay=user.get('solve_delay', 15), 
            accuracy_mode=user.get('accuracy_mode', 'advanced')
        ),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "set_speed_menu")
async def speed_menu_cb(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    await callback.message.edit_text(
        "⏱️ <b>Настройка времени решения</b>\n\nВыберете желаемую длительность прохождения одного теста (в минутах):", 
        reply_markup=get_speed_kb(user.get('solve_delay', 15)),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("save_speed_"))
async def save_speed_cb(callback: types.CallbackQuery):
    speed = int(callback.data.split("_")[-1])
    await db.update_user(callback.from_user.id, solve_delay=speed)
    await callback.answer(f"✅ Установлено: {speed} мин")
    
    user = await db.get_user(callback.from_user.id)
    await callback.message.edit_text(
        "⚙️ <b>Настройки обновлены!</b>\n\nВыберете параметр:",
        reply_markup=get_settings_kb(user.get('solve_delay', 15), user.get('accuracy_mode', 'advanced')),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "set_accuracy_menu")
async def acc_menu_cb(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    await callback.message.edit_text(
        "🎯 <b>Настройка точности AI</b>\n\nВыберете вероятность правильного ответа:", 
        reply_markup=get_accuracy_kb(user.get('accuracy_mode', 'advanced')),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("save_acc_"))
async def save_acc_cb(callback: types.CallbackQuery):
    acc = callback.data.split("_")[-1]
    await db.update_user(callback.from_user.id, accuracy_mode=acc)
    await callback.answer(f"✅ Точность обновлена")
    
    user = await db.get_user(callback.from_user.id)
    await callback.message.edit_text(
        "⚙️ <b>Настройки обновлены!</b>\n\nВыберете параметр:",
        reply_markup=get_settings_kb(user.get('solve_delay', 15), user.get('accuracy_mode', 'advanced')),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "back_to_settings")
async def back_to_settings_cb(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    await callback.message.edit_text(
        "⚙️ <b>Настройки помощника</b>\n\nВыберете параметр:",
        reply_markup=get_settings_kb(user.get('solve_delay', 15), user.get('accuracy_mode', 'advanced')),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "refresh_data")
async def refresh_data_cb(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    try:
        # Полный сброс кеша для пользователя в парсере
        await parser.get_mosreg_profile(user['token_mos'], force_refresh=True)
        await callback.answer("✅ Данные обновлены (кеш стерт)", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

@router.callback_query(F.data == "subscription_info")
async def subscription_info_cb(callback: types.CallbackQuery):
    await callback.answer("💳 Подписка: ПРЕМИУМ активен (бессрочно)", show_alert=True)

@router.callback_query(F.data == "back_to_main")
async def back_to_main_cb(callback: types.CallbackQuery):
    await callback.message.answer("🏠 Главное меню нашего помощника:", reply_markup=get_main_menu_kb())
    await callback.message.delete()
    await callback.answer()
