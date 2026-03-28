from aiogram.fsm.state import State, StatesGroup

class BotStates(StatesGroup):
    waiting_for_token = State()
    waiting_for_settings = State()
    solving_test = State()
    waiting_for_homework_date = State()
