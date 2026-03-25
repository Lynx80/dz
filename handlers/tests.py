from aiogram import Router, types, F
from database.db_service import get_user_token
from services.school_api import SchoolAPI

router = Router()

@router.message(F.text == "💻 Мои ЦДЗ тесты")
async def show_tests(message: types.Message):
    token = await get_user_token(message.from_user.id)
    if not token:
        await message.answer("⚠️ Сначала введите токен в настройках.")
        return

    msg = await message.answer("🔍 Загружаю список ваших тестов...")
    api = SchoolAPI(token)
    tests = await api.get_tests()
    
    if not tests:
        await msg.edit_text("📭 На данный момент активных ЦДЗ тестов не найдено.")
    else:
        # Пример формирования списка (логика зависит от реальной структуры JSON API)
        text = "📋 **Ваши актуальные тесты:**\n\n"
        for i, test in enumerate(tests[:10], 1):
            title = test.get("title", "Тест без названия")
            subject = test.get("subject", "Предмет не указан")
            text += f"{i}. **{subject}**: {title}\n"
        
        await msg.edit_text(text, parse_mode="Markdown")
