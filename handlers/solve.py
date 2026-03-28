from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from datetime import datetime
import asyncio
import logging
import html

from database.db import Database
from services.parser import ParserService
from keyboards.inline import get_solve_accuracy_kb, get_solve_time_kb, get_solve_final_mode_kb, get_hw_toggles_kb
from utils.states import BotStates
import re

router = Router()
db = Database()
parser = ParserService()
logger = logging.getLogger(__name__)

# --- ОБРАБОТЧИКИ ТЕКСТОВЫХ КНОПОК РЕШЕНИЯ ---

@router.message(F.text.startswith("🧠 РЕШИТЬ ВСЕ ЦДЗ"))
async def solve_all_text_msg(message: types.Message):
    match = re.search(r'\[(.*?)\]', message.text)
    if not match: return
    date_str = match.group(1)
    
    # Редирект на выбор точности для ВСЕХ
    await message.answer(
        "🧠 <b>МАССОВОЕ РЕШЕНИЕ ЦДЗ</b>\nВы выбрали решение всех доступных тестов на этот день.\n\n🎯 Выберите точность:",
        reply_markup=get_solve_accuracy_kb("all", date_str),
        parse_mode="HTML"
    )

@router.message(F.text.startswith("🔍 ЦДЗ ВЫБОРОЧНО"))
async def solve_select_text_msg(message: types.Message, state: FSMContext):
    match = re.search(r'\[(.*?)\]', message.text)
    if not match: return
    date_str = match.group(1)
    
    user = await db.get_user(message.from_user.id)
    hw_list = await parser.get_mosreg_homework(user['token_mos'], user['student_id'], date_str, mesh_id=user.get('mesh_id'))
    
    # Фильтруем только те, где есть ссылка на тест
    cdz_list = [h for h in hw_list if h.get('link') and ("test" in h['link'] or "exam" in h['link'] or "uchebnik" in h['link'])]
    
    if not cdz_list:
        await message.answer("❌ На этот день не найдено активных ЦДЗ для решения.")
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for hw in cdz_list:
        builder.button(text=f"🧠 {hw['subject'][:20]}", callback_data=f"ai_select_subj:{hw['id']}:{date_str}")
    builder.adjust(1)
    
    await message.answer(
        "🔍 <b>ВЫБОРОЧНОЕ РЕШЕНИЕ</b>\nВыберите предмет для запуска AI-решателя:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

# --- CALLBACK HANDLERS ---
async def ai_select_subj_cb(callback: types.CallbackQuery):
    _, hw_id, date_str = callback.data.split(":")
    await callback.message.edit_text(
        "🎯 Выберите точность решения:\n(Более высокая точность требует больше ресурсов)",
        reply_markup=get_solve_accuracy_kb(hw_id, date_str)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("task_acc:"))
async def task_acc_cb(callback: types.CallbackQuery):
    _, hw_id, accuracy, date_str = callback.data.split(":")
    await callback.message.edit_text(
        "⏱️ Выберите желаемое время решения (в минутах):\n"
        "(Бот растянет выполнение, имитируя человека)",
        reply_markup=get_solve_time_kb(hw_id, accuracy, date_str)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("sel_mode:"))
async def sel_mode_cb(callback: types.CallbackQuery):
    _, hw_id, accuracy, mins, date_str = callback.data.split(":")
    await callback.message.edit_text(
        "🤖 Выберите режим выполнения:",
        reply_markup=get_solve_final_mode_kb(hw_id, accuracy, mins, date_str)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("start_solve:"))
async def start_solve_cb(callback: types.CallbackQuery, state: FSMContext):
    _, hw_id, accuracy, mode, mins, date_str = callback.data.split(":")
    user_id = callback.from_user.id
    
    # 1. Получаем список предметов, чтобы найти нужную ссылку
    user = await db.get_user(user_id)
    hw_list = await parser.get_mosreg_homework(user['token_mos'], user['student_id'], date_str, mesh_id=user.get('mesh_id'))
    
    target_hw = next((h for h in hw_list if str(h['id']) == hw_id or h['subject'] == hw_id), None)
    if not target_hw or not target_hw.get('link'):
        await callback.message.edit_text("❌ Ошибка: Ссылка на тест не найдена.")
        return

    test_url = target_hw['link']
    await process_solve_logic(callback.message, user_id, test_url, accuracy, mins, mode, date_str)
    await callback.answer()

async def process_solve_logic(message, user_id, test_url, accuracy, mins, mode, date_str):
    status_msg = await message.answer("🚀 **ИНИЦИАЛИЗАЦИЯ ИИ-РЕШАТЕЛЯ**\n\n🔄 Подготовка окружения...", parse_mode="Markdown")
    
    async def update_status(text):
        try:
            # Улучшенный визуальный стиль
            header = "🧠 <b>AI SOLVER v2.0</b>\n"
            divider = "────────────────────\n"
            await status_msg.edit_text(f"{header}{divider}{html.escape(text)}", parse_mode="HTML")
        except Exception:
            pass

    try:
        res, screenshot = await parser.solve_test(
            user_id, 
            test_url, 
            accuracy_mode=accuracy, 
            solve_delay_mins=int(mins), 
            status_callback=update_status
        )
        
        if res == "NEEDS_QR":
            qr_path = await parser.init_qr_login(user_id)
            if qr_path:
                await status_msg.answer_photo(
                    types.FSInputFile(qr_path), 
                    caption="🔑 Требуется вход в МЭШ.\n\n"
                            "1. Откройте приложение 'Моя Школа' на телефоне\n"
                            "2. Перейдите в Профиль -> Вход по QR\n"
                            "3. Отсканируйте этот код\n\n"
                            "Бот автоматически продолжит после входа."
                )
                # Запускаем поллинг
                asyncio.create_task(poll_qr_status(user_id, status_msg, test_url, accuracy, mins, mode, date_str))
            else:
                await status_msg.edit_text("❌ Ошибка генерации QR-кода.")
            return

        await status_msg.edit_text(res)
        if screenshot:
            await status_msg.answer_photo(types.FSInputFile(screenshot), caption="📸 Результат выполнения теста.")
            
    except Exception as e:
        logger.error(f"Solve error: {e}")
        await status_msg.edit_text(f"❌ Критическая ошибка: {str(e)[:50]}")

async def poll_qr_status(user_id, status_msg, test_url, accuracy, mins, mode, date_str):
    for _ in range(30): # 5 минут (30 * 10 сек)
        status, token = await parser.check_qr_login_status(user_id)
        if status == "success":
            await status_msg.answer("✅ Вход выполнен! Продолжаю выполнение теста...")
            await process_solve_logic(status_msg, user_id, test_url, accuracy, mins, mode, date_str)
            return
        elif status in ["expired", "timeout", "error"]:
            await status_msg.answer("❌ Сессия входа истекла. Попробуйте снова.")
            return
        await asyncio.sleep(10)
    await status_msg.answer("❌ Время на вход истекло.")
