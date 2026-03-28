from aiogram import types
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from datetime import datetime

def get_main_menu_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📚 МОЁ ДЗ")
    builder.button(text="👤 ПРОФИЛЬ")
    builder.button(text="⚙️ НАСТРОЙКИ")
    
    # Динамический текст кнопки ДЗ
    now = datetime.now()
    weekday = now.weekday()
    hour = now.hour
    
    if weekday == 4: # Пятница
        hw_text = "📚 ДЗ НА СЕГОДНЯ" if hour < 15 else "📚 ДЗ НА ПОНЕДЕЛЬНИК"
    elif weekday == 5 or weekday == 6: # Суббота или Воскресенье
        hw_text = "📚 ДЗ НА ПОНЕДЕЛЬНИК"
    else: # Пн-Чт
        hw_text = "📚 ДЗ НА СЕГОДНЯ" if hour < 15 else "📚 ДЗ НА ЗАВТРА"
        
    builder.button(text=hw_text)
    builder.adjust(1, 2, 1)
    return builder.as_markup(resize_keyboard=True)

def get_hw_context_kb(date_str):
    """Специальное меню при просмотре расписания"""
    builder = ReplyKeyboardBuilder()
    
    # Кнопки ДЗ
    builder.row(types.KeyboardButton(text=f"🧠 РЕШИТЬ ВСЕ ЦДЗ [{date_str}]"))
    builder.row(types.KeyboardButton(text=f"🔍 ЦДЗ ВЫБОРОЧНО [{date_str}]"))
    
    # Кнопки навигации (стандартные)
    builder.row(types.KeyboardButton(text="👤 ПРОФИЛЬ"), types.KeyboardButton(text="⚙️ НАСТРОЙКИ"))
    builder.row(types.KeyboardButton(text="🏠 ГЛАВНОЕ МЕНЮ"))
    
    return builder.as_markup(resize_keyboard=True)

def get_hw_reply_kb():
    # На случай если нужно после ошибки
    return get_main_menu_kb()

def get_nav_reply_kb():
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🔙 НАЗАД"), types.KeyboardButton(text="🏠 МЕНЮ"))
    return builder.as_markup(resize_keyboard=True)
