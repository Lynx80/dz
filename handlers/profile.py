from aiogram import Router, types, F
from database.db_service import get_user_profile, get_user_token
from services.school_api import SchoolAPI

router = Router()

@router.message(F.text == "👤 Профиль")
async def show_profile(message: types.Message):
    user = await get_user_profile(message.from_user.id)
    if not user or not user["token"]:
        await message.answer("⚠️ Вы не авторизованы. Перейдите в '⚙️ Настройки'.")
        return

    text = (
        "👤 **Ваш профиль:**\n\n"
        f"🔹 **Имя**: {user['first_name'] or 'Не загружено'}\n"
        f"🔹 **Фамилия**: {user['last_name'] or 'Не загружено'}\n"
        f"🔹 **Класс**: {user['class_name'] or 'Не загружено'}\n\n"
        "💡 Нажмите '🔄 Обновить данные', если информация устарела."
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text == "🔄 Обновить данные")
async def refresh_data(message: types.Message):
    token = await get_user_token(message.from_user.id)
    if not token:
        await message.answer("⚠️ Сначала введите токен в настройках.")
        return

    msg = await message.answer("🔄 Обновляю данные с портала...")
    api = SchoolAPI(token)
    profile = await api.get_profile()
    
    if profile:
        from database.db_service import update_user_profile
        await update_user_profile(
            message.from_user.id, 
            profile["first_name"], 
            profile["last_name"], 
            profile["class_name"]
        )
        await msg.edit_text("✅ Данные успешно обновлены!")
    else:
        await msg.edit_text("❌ Ошибка при обновлении. Проверьте актуальность токена.")
