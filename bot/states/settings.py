from aiogram.fsm.state import State, StatesGroup


class SettingsSG(StatesGroup):
    menu = State()
    edit_batch_size = State()
    edit_reminder_time = State()
    edit_tz = State()
