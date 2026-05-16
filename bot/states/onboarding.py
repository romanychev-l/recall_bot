from aiogram.fsm.state import State, StatesGroup


class OnboardSG(StatesGroup):
    choose_start = State()
    enter_skip_n = State()
