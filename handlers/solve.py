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
    
    # Улучшенный поиск ЦДЗ: проверяем все вложения и текст
    cdz_list = []
    for h in hw_list:
        description = h.get('description', '').lower()
        test_keywords = ["test", "exam", "uchebnik", "edu-content", "resh.edu", "physicon", "onlinetestpad"]
        
        # Проверяем все ссылки в материалах
        found_test_link = None
        for m in h.get('materials', []):
            m_link = m.get('link', '').lower()
            if m_link and any(kw in m_link for kw in test_keywords):
                found_test_link = m.get('link')
                break
        
        # Если в материалах не нашли, смотрим основной link
        main_link = h.get('link', '').lower()
        if not found_test_link and main_link and any(kw in main_link for kw in test_keywords):
            found_test_link = h.get('link')
            
        # Эвристика по ключевым словам в тексте (если есть хоть какая-то ссылка)
        if not found_test_link and h.get('link'):
            if any(word in description for word in ["цдз", "мэш", "тест"]):
                found_test_link = h.get('link')
        
        if found_test_link:
            h['link'] = found_test_link
            cdz_list.append(h)
    
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

@router.callback_query(F.data.startswith("solve_all_inline:"))
async def solve_all_inline_cb(callback: types.CallbackQuery):
    date_str = callback.data.split(":")[1]
    await callback.message.answer(
        "🧠 <b>МАССОВОЕ РЕШЕНИЕ ЦДЗ</b>\nВы выбрали решение всех доступных тестов на этот день.\n\n🎯 Выберите точность:",
        reply_markup=get_solve_accuracy_kb("all", date_str),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("solve_select_inline:"))
async def solve_select_inline_cb(callback: types.CallbackQuery):
    date_str = callback.data.split(":")[1]
    user = await db.get_user(callback.from_user.id)
    hw_list = await parser.get_mosreg_homework(user['token_mos'], user['student_id'], date_str, mesh_id=user.get('mesh_id'))
    
    # Улучшенный поиск ЦДЗ: проверяем все вложения и текст
    cdz_list = []
    for h in hw_list:
        description = h.get('description', '').lower()
        test_keywords = ["test", "exam", "uchebnik", "edu-content", "resh.edu", "physicon", "onlinetestpad"]
        
        found_test_link = None
        for m in h.get('materials', []):
            m_link = m.get('link', '').lower()
            if m_link and any(kw in m_link for kw in test_keywords):
                found_test_link = m.get('link')
                break
        
        main_link = h.get('link', '').lower()
        if not found_test_link and main_link and any(kw in main_link for kw in test_keywords):
            found_test_link = h.get('link')
            
        if not found_test_link and h.get('link'):
            if any(word in description for word in ["цдз", "мэш", "тест"]):
                found_test_link = h.get('link')
        
        if found_test_link:
            h['link'] = found_test_link
            cdz_list.append(h)
    
    if not cdz_list:
        await callback.answer("❌ ЦДЗ не найдены", show_alert=True)
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for hw in cdz_list:
        builder.button(text=f"🧠 {hw['subject'][:20]}", callback_data=f"ai_select_subj:{hw['id']}:{date_str}")
    builder.adjust(1)
    
    await callback.message.answer(
        "🔍 <b>ВЫБОРОЧНОЕ РЕШЕНИЕ</b>\nВыберите предмет:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

# --- CALLBACK HANDLERS ---
@router.callback_query(F.data.startswith("ai_select_subj:"))
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

# Кэш для хранения параметров активных QR-сессий (нужно для кнопки обновления, т.к. URL слишком длинный)
qr_data_cache = {}

@router.callback_query(F.data.startswith("solve_qr_refresh:"))
async def solve_qr_refresh_cb(callback: types.CallbackQuery):
    _, msg_id = callback.data.split(":")
    data = qr_data_cache.get(int(msg_id))
    
    if not data:
        await callback.answer("❌ Данные сессии истекли. Запустите решение заново.", show_alert=True)
        return
        
    await callback.answer("🔄 Обновляю QR-код...")
    # Удаляем старое фото, чтобы не путать
    try: await callback.message.delete()
    except: pass
    
    await process_solve_logic(
        callback.message, 
        data['user_id'], 
        data['test_url'], 
        data['accuracy'], 
        data['mins'], 
        data['mode'], 
        data['date_str']
    )

async def process_solve_logic(message, user_id, test_url, accuracy, mins, mode, date_str, is_resume=False):
    status_msg = await message.answer("🚀 **ИНИЦИАЛИЗАЦИЯ ИИ-РЕШАТЕЛЯ**\n\n🔄 Подготовка окружения...", parse_mode="Markdown")
    
    async def update_status(text):
        try:
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
            if is_resume:
                await status_msg.edit_text("❌ Авторизация через QR не удалась или не была распознана сайтом. Попробуйте еще раз.")
                return
                
            qr_path = await parser.init_qr_login(user_id, test_url)
            if qr_path:
                from aiogram.utils.keyboard import InlineKeyboardBuilder
                kb = InlineKeyboardBuilder()
                # Сохраняем данные для кнопки обновления
                qr_data_cache[status_msg.message_id] = {
                    'user_id': user_id, 'test_url': test_url, 'accuracy': accuracy, 
                    'mins': mins, 'mode': mode, 'date_str': date_str
                }
                kb.button(text="🔄 Обновить QR-код", callback_data=f"solve_qr_refresh:{status_msg.message_id}")
                
                await status_msg.answer_photo(
                    types.FSInputFile(qr_path), 
                    caption="🔑 **ТРЕБУЕТСЯ ВХОД В МЭШ**\n\n"
                            "1️⃣ Откройте приложение «Моя Школа» на телефоне\n"
                            "2️⃣ Перейдите в **Профиль → Вход по QR**\n"
                            "3️⃣ Отсканируйте этот код\n\n"
                            "⏳ У вас есть 10 минут. Бот автоматически продолжит работу после входа.",
                    reply_markup=kb.as_markup(),
                    parse_mode="Markdown"
                )
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
    for _ in range(60): # 10 минут (60 * 10 сек)
        # Проверяем, не удалил ли пользователь этот статус (например, рефрешнул)
        if status_msg.message_id in qr_data_cache and qr_data_cache[status_msg.message_id].get('cancelled'):
            return

        status, token = await parser.check_qr_login_status(user_id)
        if status == "success":
            await status_msg.answer("✅ Бот авторизован и приступает к выполнению теста!")
            # Очищаем кэш после успеха
            qr_data_cache.pop(status_msg.message_id, None)
            await process_solve_logic(status_msg, user_id, test_url, accuracy, mins, mode, date_str, is_resume=True)
            return
        elif status in ["expired", "timeout", "error"]:
            await status_msg.answer("❌ Сессия входа истекла или произошла ошибка. Попробуйте снова.")
            qr_data_cache.pop(status_msg.message_id, None)
            return
        await asyncio.sleep(10)
    await status_msg.answer("❌ Время на вход (10 минут) истекло.")
    qr_data_cache.pop(status_msg.message_id, None)
