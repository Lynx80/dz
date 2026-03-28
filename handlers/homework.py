from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from datetime import datetime, timedelta
import logging

from database.db import Database
from services.parser import ParserService, MosregAuthError
from keyboards.reply import get_hw_reply_kb, get_main_menu_kb, get_hw_context_kb
from keyboards.inline import get_week_kb, get_hw_toggles_kb, get_calendar_kb, get_date_ribbon_kb
import re
import html
from utils.helpers import classify_hw

router = Router()
db = Database()
parser = ParserService()
logger = logging.getLogger(__name__)

# Словарь красивых сокращений для кнопок
SMART_SUBJECT_NAMES = {
    "обществознание": "Общество",
    "литература": "Лит-ра",
    "физическая культура": "Физ-ра",
    "английский язык": "Английский",
    "математика": "Математика",
    "информатика": "Инфо",
    "вероятность и статистика": "Статистика",
    "изобразительное искусство": "Изо",
    "технология": "Техно",
    "география": "Гео",
    "биология": "Био",
    "алгебра и начала математического анализа": "Алгебра",
}

async def show_day_homework(message, user_id, date_str, page=0, force_refresh=False):
    user = await db.get_user(user_id)
    if not user: return
    
    try:
        # Теперь получаем ПОЛНОЕ РАСПИСАНИЕ (уроки + ДЗ внутри)
        lesson_list = await parser.get_mosreg_schedule(
            user['token_mos'], 
            user['student_id'], 
            date_str, 
            mesh_id=user.get('mesh_id'),
            force_refresh=force_refresh
        )
        
        # Фильтруем: уроки vs праздники
        real_lessons = [l for l in lesson_list if not l.get('is_holiday')]
        holiday_events = [l for l in lesson_list if l.get('is_holiday')]
        
        # Определяем статус дня
        dt_obj = datetime.strptime(date_str, '%Y-%m-%d')
        is_weekend = dt_obj.weekday() >= 5
        day_off_text = ""
        
        if not real_lessons:
            if holiday_events:
                h_names = ", ".join(set([h['subject'] for h in holiday_events]))
                day_off_text = f"⛱️ <b>{h_names.upper()}!</b>\nОтдыхай, уроков официально нет. 🔥"
            elif is_weekend:
                day_off_text = "🔴 <b>ВЫХОДНОЙ!</b>\nУроков нет, самое время набраться сил. 💪"
            else:
                day_off_text = "🍃 <b>СВОБОДНЫЙ ДЕНЬ!</b>\nВ расписании пусто, отдыхай или займись своими делами. ✨"

        if day_off_text:
            text = f"📅 <b>РАСПИСАНИЕ НА {date_str}</b>\n\n"
            text += f"<blockquote>{day_off_text}</blockquote>\n"
            
            # Если все же есть ДЗ (перенесенное или спецзадание)
            if any(l.get('has_hw') for l in lesson_list):
                 text += "<i>P.S. Хотя уроков нет, я нашел задания:</i>\n"
                 # (можно вывести список ДЗ если нужно, но обычно на выходных пусто)
            
            kb = get_date_ribbon_kb(dt_obj)
            reply_kb = get_hw_context_kb(date_str)
            
            if isinstance(message, types.Message):
                await message.answer(text, reply_markup=reply_kb, parse_mode="HTML")
                await message.answer("👆 Выберите другой день в ленте:", reply_markup=kb, parse_mode="HTML")
            else:
                try:
                    await message.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
                except Exception:
                    pass
            return

        # Обработка данных для отображения (если уроки есть)
        done_count = 0
        hw_total = 0
        for l in lesson_list:
            hw_desc = l.get('hw', '').strip()
            materials = l.get('materials', [])
            
            # Помечаем, есть ли ДЗ
            l['has_hw'] = bool(hw_desc and hw_desc not in ['', 'без д/з', 'Нет заданий']) or bool(materials)
            
            # Синхронизация: проверяем по hw_hash
            l['is_done'] = await db.is_hw_completed(user_id, date_str, l.get('hw_hash', 'no_hw'))
            
            if l['has_hw']:
                hw_total += 1
                if l['is_done']: done_count += 1
                
            # Эвристика для ЦДЗ
            l['is_ec'] = "цдз" in hw_desc.lower() or "мэш" in hw_desc.lower() or "http" in hw_desc.lower()

        # Расчет прогресса и слогана
        progress_footer = ""
        percent = 0
        if hw_total > 0:
            percent = int((done_count / hw_total) * 100)
            filled = int(percent / 10)
            bar = "█" * filled + "░" * (10 - filled)
            
            # Слоганы
            if percent == 0: slogan = "🚀 Пора начинать! Удачи сегодня."
            elif percent < 50: slogan = "📈 Неплохой старт! Двигайся в том же темпе."
            elif percent < 75: slogan = "🌓 Половина пути пройдена! Ты молодец."
            elif percent < 100: slogan = "🔥 Финишная прямая! Еще чуть-чуть."
            else: slogan = "🏆 ИДЕАЛЬНО! Все задания выполнены. Отдыхай!"
            
            progress_footer = f"────────────────────\n📊 <b>Прогресс ДЗ:</b> [{bar}] {percent}%\n💬 <i>{slogan}</i>\n"

        total = len(lesson_list)
        page_size = 8
        start = page * page_size
        end = start + page_size
        current_lessons = lesson_list[start:end]

        # Заголовок со сводкой
        header = f"📅 <b>РАСПИСАНИЕ НА {date_str}</b>\n"
        header += f"📓 Уроков: {total} | 📚 С заданиями: {hw_total}\n"
        
        # Доп. инфо от себя (Первый урок)
        if total > 0 and page == 0:
            first_lesson = lesson_list[0]
            header += f"🔔 Первый урок: <code>{first_lesson['time'].split('-')[0]}</code>\n"
        header += "\n"

        text = header
        shown_hw = {} # {subject: last_hw_text}
        
        for i, l in enumerate(current_lessons):
            # 1. Заголовок урока (номер, статус, предмет)
            subj_clean = l['subject'].lower().strip()
            # Пробуем найти красивое сокращение
            subj = SMART_SUBJECT_NAMES.get(subj_clean)
            if not subj:
                # Если нет в словаре - режем по классике
                subj_title = l['subject'].capitalize()
                subj = re.split(r'\(|-', subj_title)[0].strip()
            else:
                # Нашли сокращение! (С большой буквы)
                subj = subj.capitalize()
            
            time_info = f"<code>{l['time']}</code>"
            room_info = f" (каб. {l['room']})" if l['room'] else ""
            
            status = ""
            if l['has_hw']:
                status = "✅" if l['is_done'] else "🔴"
            else:
                status = "🕊️" # Нет задания
            
            text += f"{i+start+1}. {status} <b>{subj}</b>\n"
            text += f"   {time_info}{room_info}\n"
            
            # 2. Описание задания
            if l['has_hw']:
                hw_desc = l['hw'].strip()
                materials = l['materials']
                
                # Если текста нет, но есть материалы
                if not hw_desc and materials:
                    hw_desc = f"📚 {materials[0]['title']}"

                # ДУБЛИКАТЫ: Проверяем, было ли такое же задание выше для этого предмета
                is_duplicate = False
                if subj in shown_hw and shown_hw[subj] == hw_desc and len(hw_desc) > 5:
                    is_duplicate = True
                else:
                    shown_hw[subj] = hw_desc

                if is_duplicate:
                    text += "   <blockquote>👆 <i>Задание такое же, как выше</i></blockquote>\n"
                else:
                    # Извлекаем ссылки
                    links = [l.rstrip('.;:,') for l in re.findall(r'https?://[^\s<>"]+', hw_desc)]
                    clean_desc = re.sub(r'https?://[^\s<>"]+', '', hw_desc).strip('; .')
                    
                    text += f"   <blockquote>{html.escape(clean_desc or 'Задание в материалах')}</blockquote>"
                    
                    # Добавляем ссылки-кнопки (все уникальные)
                    all_links = []
                    # Сначала из материалов (они обычно важнее)
                    for m in materials:
                        if m.get('link') and m['link'] not in all_links: all_links.append(m['link'])
                    # Потом из текста
                    for lnk in links:
                        if lnk not in all_links: all_links.append(lnk)

                    if all_links:
                        text += "   "
                        for idx, link in enumerate(all_links):
                            link_text = "🔗 Ссылка"
                            if any(x in link.lower() for x in ["test", "exam", "uchebnik", "edu-content", "resh.edu"]): 
                                link_text = f"🧠 Тест {idx+1}" if len(all_links) > 1 else "🧠 Тест"
                            else:
                                link_text = f"🔗 Ссылка {idx+1}" if len(all_links) > 1 else "🔗 Ссылка"
                            
                            text += f" <a href='{link}'>{link_text}</a>"
                        text += "\n"
            else:
                text += "   <i>Нет заданий</i>\n"
            
            text += "\n"
            
        # Добавляем прогресс в конец
        text += progress_footer
        
        kb = get_hw_toggles_kb(lesson_list, date_str, page=page, page_size=page_size)
        reply_kb = get_hw_context_kb(date_str)
        
        # Чтобы меню точно обновилось, отправляем его с основным сообщением
        if isinstance(message, types.Message):
            # Отправляем сообщение и устанавливаем меню кнопок
            await message.answer(text, reply_markup=reply_kb, parse_mode="HTML")
            await message.answer("👆 Управление статусом уроков:", reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
        else: # CallbackQuery
            # Обновляем инлайн-меню (тихо)
            try:
                await message.message.edit_text(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
            except Exception:
                pass # Если текст/кнопки не поменялись
            
            # Решаем дилемму с кнопками снизу (чтобы не было спама)
            # Мы обновляем нижнее меню только при ЯВНОМ выборе даты или если это первое сообщение
            silent_callbacks = ["hw_done:", "hw_page:", "refresh_hw_list:"]
            is_silent = any(x in (getattr(message, 'data', '') or '') for x in silent_callbacks)
            
            if not is_silent:
                # Смена даты! Принудительно обновляем нижнее меню кнопок ("Решить все" и т.д.)
                # Чтобы не было много спама, используем лаконичный текст
                await message.message.answer("🗂️ Меню управления обновлено", reply_markup=reply_kb)
            
            if not isinstance(message, types.Message):
                # Для колбэков всегда отвечаем "тихо" во всплывающем окне
                await message.answer()

    except MosregAuthError:
        error_text = "⚠️ Ошибка: Токен устарел. Перезапустите бота /start."
        if isinstance(message, types.Message): await message.answer(error_text)
        else: await message.message.edit_text(error_text)
    except Exception as e:
        logger.error(f"HW fetch error: {e}")
        error_text = f"❌ Ошибка загрузки ДЗ: {str(e)[:50]}"
        if isinstance(message, types.Message): await message.answer(error_text)
        else: await message.answer(error_text)

@router.message(F.text == "🏠 ГЛАВНОЕ МЕНЮ")
async def back_to_main(message: types.Message):
    await message.answer("Возвращаюсь в главное меню.", reply_markup=get_main_menu_kb())

@router.message(F.text.startswith("📚 МОЁ ДЗ"))
async def my_hw_menu(message: types.Message):
    await message.answer("Выберите неделю:", reply_markup=get_week_kb())

@router.message(F.text.startswith("📚 ДЗ НА "))
async def quick_hw(message: types.Message):
    t = message.text
    now = datetime.now()
    if "СЕГОДНЯ" in t:
        date = now
    elif "ЗАВТРА" in t:
        # Пятница -> Понедельник
        if now.weekday() == 4: date = now + timedelta(days=3)
        # Суббота -> Понедельник
        elif now.weekday() == 5: date = now + timedelta(days=2)
        else: date = now + timedelta(days=1)
    elif "ПОНЕДЕЛЬНИК" in t:
        days_ahead = 0 - now.weekday()
        if days_ahead <= 0: days_ahead += 7
        date = now + timedelta(days=days_ahead)
    else: date = now
    
    date_str = date.strftime('%Y-%m-%d')
    await show_day_homework(message, message.from_user.id, date_str)

@router.callback_query(F.data.startswith("cal_nav_"))
async def calendar_nav_cb(callback: types.CallbackQuery):
    _, _, month, year = callback.data.split("_")
    await callback.message.edit_reply_markup(reply_markup=get_calendar_kb(int(month), int(year)))
    await callback.answer()

@router.callback_query(F.data.startswith("manual_"))
async def day_select_cb(callback: types.CallbackQuery):
    date_str = callback.data.split("_")[1]
    await show_day_homework(callback, callback.from_user.id, date_str)
    await callback.answer()

@router.callback_query(F.data == "week_curr")
async def week_curr_cb(callback: types.CallbackQuery, state: FSMContext):
    # Возвращаемся к ленте текущей даты
    await state.update_data(ribbon_anchor=datetime.now().strftime('%Y-%m-%d'))
    await callback.message.edit_reply_markup(reply_markup=get_date_ribbon_kb())
    await callback.answer()

@router.callback_query(F.data == "full_calendar")
async def full_calendar_cb(callback: types.CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=get_calendar_kb())
    await callback.answer()

@router.callback_query(F.data.startswith("ribbon_"))
async def ribbon_nav_cb(callback: types.CallbackQuery, state: FSMContext):
    # Логика смещения ленты
    data = await state.get_data()
    current_date_str = data.get('ribbon_anchor', datetime.now().strftime('%Y-%m-%d'))
    current_date = datetime.strptime(current_date_str, '%Y-%m-%d')
    
    if "prev" in callback.data:
        new_date = current_date - timedelta(days=7)
    else:
        new_date = current_date + timedelta(days=7)
        
    await state.update_data(ribbon_anchor=new_date.strftime('%Y-%m-%d'))
    await callback.message.edit_reply_markup(reply_markup=get_date_ribbon_kb(new_date))
    await callback.answer()

@router.callback_query(F.data.startswith("hw_page:"))
async def hw_pagination_cb(callback: types.CallbackQuery):
    _, date_str, page = callback.data.split(":")
    await show_day_homework(callback, callback.from_user.id, date_str, page=int(page))
    await callback.answer()

@router.callback_query(F.data.startswith("hw_done:"))
async def toggle_hw_cb(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    date_str, hw_hash = parts[1], parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0
    
    user_id = callback.from_user.id
    
    is_done = await db.is_hw_completed(user_id, date_str, hw_hash)
    if is_done:
        await db.unmark_hw_completed(user_id, date_str, hw_hash)
    else:
        await db.mark_hw_completed(user_id, date_str, hw_hash)
    
    await callback.answer("Статус обновлен")
    await show_day_homework(callback, user_id, date_str, page=page)

@router.callback_query(F.data.startswith("refresh_hw_list:"))
async def refresh_hw_list_cb(callback: types.CallbackQuery):
    date_str = callback.data.split(":")[1]
    # Принудительное обновление для обхода кеша
    await show_day_homework(callback, callback.from_user.id, date_str, force_refresh=True)
    await callback.answer("⏳ Обновлено из портала")
