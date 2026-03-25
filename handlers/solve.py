from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db_service import get_user_token
from services.solver import TestSolver

router = Router()

class SolveStates(StatesGroup):
    waiting_url = State()

@router.message(F.text == "🤖 Авторешение")
async def start_solve(message: types.Message, state: FSMContext):
    token = await get_user_token(message.from_user.id)
    if not token:
        await message.answer("⚠️ Сначала введите токен в '⚙️ Настройки'.")
        return
    
    await message.answer("🔗 Отправьте ссылку на тест (МЭШ или ЦДЗ):")
    await state.set_state(SolveStates.waiting_url)

@router.message(SolveStates.waiting_url)
async def process_test_url(message: types.Message, state: FSMContext):
    url = message.text.strip()
    if not url.startswith("http"):
        await message.answer("❌ Это не похоже на правильную ссылку. Попробуйте еще раз:")
        return

    token = await get_user_token(message.from_user.id)
    msg = await message.answer("🚀 Начинаю авторешение... Это может занять пару минут.")
    
    async def update_status(text):
        try:
            await msg.edit_text(text)
        except Exception:
            pass

    solver = TestSolver(token, url)
    success = await solver.solve(status_callback=update_status)
    
    if success:
        await message.answer("📊 Готово! Вы можете проверить результаты в своем личном кабинете.")
    else:
        await message.answer("⚠️ Не удалось завершить тест полностью. Проверьте ссылку или токен.")
    
    await state.clear()
