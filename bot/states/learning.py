from aiogram.fsm.state import State, StatesGroup


class LearnSG(StatesGroup):
    waiting_answer = State()
