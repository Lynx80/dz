from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta

import calendar

def get_calendar_kb(month=None, year=None):
    """Генерирует инлайновый календарь для выбора даты."""
    now = datetime.now()
    if month is None: month = now.month
    if year is None: year = now.year

    builder = InlineKeyboardBuilder()
    
    # 1. Заголовок месяца и года
    month_name = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"][month-1]
    builder.row(types.InlineKeyboardButton(text=f"📅 {month_name} {year}", callback_data="ignore"))

    # 2. Дни недели
    days_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    builder.row(*[types.InlineKeyboardButton(text=d, callback_data="ignore") for d in days_ru])

    # 3. Числа
    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        row = []
        for i, day in enumerate(week):
            if day == 0:
                row.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                d_str = f"{year}-{month:02d}-{day:02d}"
                text = str(day)
                is_weekend = (i >= 5) # Сб = 5, Вс = 6
                
                if day == now.day and month == now.month and year == now.year:
                    text = f"📍{day}"
                elif is_weekend:
                    text = f"{day}🔴"
                    
                row.append(types.InlineKeyboardButton(text=text, callback_data=f"manual_{d_str}"))
        builder.row(*row)

    # 4. Навигация
    prev_m, prev_y = (12, year-1) if month == 1 else (month-1, year)
    next_m, next_y = (1, year+1) if month == 12 else (month+1, year)
    
    builder.row(
        types.InlineKeyboardButton(text="⬅️", callback_data=f"cal_nav_{prev_m}_{prev_y}"),
        types.InlineKeyboardButton(text="📋 К ЛЕНТЕ", callback_data="week_curr"),
        types.InlineKeyboardButton(text="➡️", callback_data=f"cal_nav_{next_m}_{next_y}")
    )
    
    return builder.as_markup()

def get_date_ribbon_kb(start_date=None):
    """Генерирует компактную ленту из 7 дней."""
    if start_date is None: start_date = datetime.now()
    builder = InlineKeyboardBuilder()
    
    # Расчитываем начало ленты (текущий день в центре)
    ribbon_start = start_date - timedelta(days=3)
    days_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    for i in range(7):
        d = ribbon_start + timedelta(days=i)
        date_str = d.strftime('%Y-%m-%d')
        day_name = days_ru[d.weekday()]
        
        # Подсветка дня (Компактно для 7 кнопок)
        num = d.day
        is_weekend = d.weekday() >= 5
        
        if d.date() == datetime.now().date():
            text = f"📍{num}"
        elif d.date() == start_date.date():
            text = f"·{day_name}{num}·"
        elif is_weekend:
            text = f"🔴{day_name}{num}"
        else:
            text = f"{day_name} {num}"
            
        builder.button(text=text, callback_data=f"manual_{date_str}")
    
    builder.adjust(7) # Все дни в одну строку
    
    builder.row(
        types.InlineKeyboardButton(text="⬅️ Назад", callback_data="ribbon_prev"),
        types.InlineKeyboardButton(text="📅 Календарь", callback_data="full_calendar"),
        types.InlineKeyboardButton(text="Вперед ➡️", callback_data="ribbon_next")
    )
    
    return builder.as_markup()

def get_week_kb(prefix="week"):
    return get_date_ribbon_kb()

def get_hw_toggles_kb(lesson_list, date_str, page=0, page_size=8):
    """Инлайн-клавиатура с пагинацией и управлением статусом (для полного расписания)"""
    builder = InlineKeyboardBuilder()
    
    # 1. Расчет пагинации
    total = len(lesson_list)
    start_idx = page * page_size
    end_idx = start_idx + page_size
    current_page_items = lesson_list[start_idx:end_idx]
    
    # 2. Кнопки предметов текущей страницы (только если есть ДЗ)
    seen_subjects = set()
    
    # Буфер для компактных предметов (без доп. кнопок)
    compact_buffer = []

    def flush_buffer():
        if compact_buffer:
            builder.row(*compact_buffer)
            compact_buffer.clear()

    for l in current_page_items:
        if l.get('has_hw'):
            # Дедупликация: Не показываем одинаковые предметы с одинаковым дз
            hw_str = str(l.get('hw', '')).strip().lower()
            subj_clean = str(l.get('subject', '')).strip().lower()
            subj_key = (subj_clean, hw_str)
            
            if subj_key in seen_subjects:
                continue
            seen_subjects.add(subj_key)

            status_icon = "✅" if l['is_done'] else "🔴"
            subj_name = l['subject']
            if len(subj_name) > 13: subj_name = subj_name[:11] + ".."
            
            # Используем hw_hash вместо l['id'] для синхронизации статуса дублей
            h_hash = l.get('hw_hash', 'no_hw')
            toggle_btn = types.InlineKeyboardButton(text=f"{status_icon} {subj_name}", callback_data=f"hw_done:{date_str}:{h_hash}:{page}")
            
            mats = l.get('materials', [])
            if mats:
                # Если у предмета есть вложения - он должен быть на отдельной строке
                flush_buffer()
                builder.row(toggle_btn)
                
                # Добавляем вложения (кнопки) по 2 штуки
                mat_buttons = []
                for m in mats:
                    t = m.get('title', '📎 Файл')
                    if len(t) > 20: t = t[:18] + ".."
                    mat_buttons.append(types.InlineKeyboardButton(text=t, url=m.get('link')))
                
                for i in range(0, len(mat_buttons), 2):
                    builder.row(*mat_buttons[i:i+2])
            else:
                # Если вложений нет - добавляем в буфер для 2-колоночного ряда
                compact_buffer.append(toggle_btn)
                if len(compact_buffer) == 2:
                    flush_buffer()

    # Финальный сброс буфера (если остался нечетный предмет)
    flush_buffer()
    
    # 3. Кнопки пагинации
    nav_row = []
    if page > 0:
        nav_row.append(types.InlineKeyboardButton(text="⬅️ Пред.", callback_data=f"hw_page:{date_str}:{page-1}"))
    if end_idx < total:
        nav_row.append(types.InlineKeyboardButton(text="След. ➡️", callback_data=f"hw_page:{date_str}:{page+1}"))
    if nav_row:
        builder.row(*nav_row)

    # 4. Кнопки быстрого решения для текущей страницы
    for l in current_page_items:
        if l.get('has_hw') and not l['is_done'] and not l.get('is_ec'):
            desc = l.get('hw', '').lower()
            if any(x in desc for x in ['http', 'тест', 'цдз', 'мэш']) or (l.get('materials') and any('http' in m.get('link', '') for m in l['materials'])):
                 builder.row(types.InlineKeyboardButton(
                     text=f"🧠 РЕШИТЬ: {l['subject'][:15]}", 
                     callback_data=f"ai_select_subj:{l['id']}:{date_str}"
                 ))
    
    # 6. Кнопка ОБНОВИТЬ
    builder.row(types.InlineKeyboardButton(text="🔄 ОБНОВИТЬ СПИСОК", callback_data=f"refresh_hw_list:{date_str}"))
    
    return builder.as_markup()

def get_solve_accuracy_kb(task_id, date_str, is_batch=False):
    """Клавиатура выбора точности решения (Шаг 2)"""
    builder = InlineKeyboardBuilder()
    prefix = "batch_acc" if is_batch else f"task_acc:{task_id}"
    
    builder.button(text="⭐ Базовая (70%)", callback_data=f"{prefix}:basic:{date_str}")
    builder.button(text="⭐⭐ Продвинутая (85%)", callback_data=f"{prefix}:advanced:{date_str}")
    builder.button(text="⭐⭐⭐ Идеальная (95%)", callback_data=f"{prefix}:perfect:{date_str}")
    builder.button(text="🔙 Назад к списку", callback_data=f"manual_{date_str}")
    
    builder.adjust(1)
    return builder.as_markup()

def get_solve_time_kb(task_id, accuracy, date_str):
    """Клавиатура выбора времени (Шаг 3)"""
    builder = InlineKeyboardBuilder()
    options = [5, 10, 15, 25]
    for mins in options:
        builder.button(text=f"⏱️ {mins} мин", callback_data=f"sel_mode:{task_id}:{accuracy}:{mins}:{date_str}")
        
    builder.button(text="🔙 Назад", callback_data=f"ai_select_subj:{task_id}:{date_str}")
    builder.adjust(2)
    return builder.as_markup()

def get_solve_final_mode_kb(task_id, accuracy, mins, date_str):
    """Клавиатура выбора режима (Шаг 4)"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🤖 С имитацией человека", callback_data=f"start_solve:{task_id}:{accuracy}:human:{mins}:{date_str}")
    builder.button(text="⏱️ Обычный режим", callback_data=f"start_solve:{task_id}:{accuracy}:normal:{mins}:{date_str}")
    builder.button(text="🔙 Назад", callback_data=f"task_acc:{task_id}:{accuracy}:{date_str}")
    builder.adjust(1)
    return builder.as_markup()

def get_settings_kb(solve_delay=15, accuracy_mode="advanced"):
    builder = InlineKeyboardBuilder()
    acc_text = {"basic": "70+%", "advanced": "80+%", "perfect": "90+%"}.get(accuracy_mode, "80+%")
    builder.button(text=f"⏱ ВРЕМЯ РЕШЕНИЯ: {solve_delay} МИН", callback_data="set_speed_menu")
    builder.button(text=f"🎯 ТОЧНОСТЬ AI: {acc_text}", callback_data="set_accuracy_menu")
    builder.button(text="🔄 ОБНОВИТЬ ДАННЫЕ", callback_data="refresh_data")
    builder.button(text="💳 ПОДПИСКА", callback_data="subscription_info")
    builder.button(text="🔙 НАЗАД В МЕНЮ", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_profile_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 ОБНОВИТЬ ПРОФИЛЬ", callback_data="refresh_profile_data")
    builder.button(text="🗑 УДАЛИТЬ ТОКЕН", callback_data="delete_token_confirm")
    builder.button(text="🔙 НАЗАД", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_speed_kb(current_speed=15):
    builder = InlineKeyboardBuilder()
    for s in [1, 5, 10, 15, 20, 25]:
        text = f"✅ {s} МИН" if s == current_speed else f"{s} МИН"
        if s == 15: text += " (ПО УМОЛЧАНИЮ)"
        builder.button(text=text, callback_data=f"save_speed_{s}")
    builder.button(text="🔙 НАЗАД", callback_data="back_to_settings")
    builder.adjust(1)
    return builder.as_markup()

def get_accuracy_kb(current_acc="advanced"):
    builder = InlineKeyboardBuilder()
    modes = [("basic", "🥉 БАЗОВЫЙ (70+%)"), ("advanced", "🥈 СТАНДАРТ (80+%)"), ("perfect", "🥇 МАКСИМУМ (95+%)")]
    for m_id, m_text in modes:
        text = f"✅ {m_text}" if m_id == current_acc else m_text
        if m_id == "advanced" and m_id != current_acc: text += " (AUTO)"
        builder.button(text=text, callback_data=f"save_acc_{m_id}")
    builder.button(text="🔙 НАЗАД", callback_data="back_to_settings")
    builder.adjust(1)
    return builder.as_markup()

def get_token_help_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="ЧТО ТАКОЕ ТОКЕН ❓", callback_data="what_is_token")
    builder.button(text="🔙 ВЕРНУТЬСЯ В ГЛАВНОЕ МЕНЮ", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()
