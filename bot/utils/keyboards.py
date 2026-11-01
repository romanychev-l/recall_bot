from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from bot.domain.parts_of_speech import ALL_POS, PARTS_OF_SPEECH, POS_BITS


def onboarding_kb(i18n) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=i18n.button.start_zero(), callback_data="onboard:zero")],
        [InlineKeyboardButton(text=i18n.button.start_skip(), callback_data="onboard:skip")],
    ])


def answer_actions_kb(i18n, word_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=i18n.button.dont_know(), callback_data=f"card:dontknow:{word_id}"
            ),
            InlineKeyboardButton(
                text=i18n.button.skip(), callback_data=f"card:skip:{word_id}"
            ),
        ],
    ])


def learning_actions_kb(i18n, *, can_continue: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    if can_continue:
        buttons.append([
            InlineKeyboardButton(text=i18n.button.continue_learning(), callback_data="learn:continue")
        ])
    buttons.append([
        InlineKeyboardButton(text=i18n.button.more_words(), callback_data="learn:more")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def settings_kb(i18n) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=i18n.button.settings_batch(), callback_data="settings:batch")],
        [InlineKeyboardButton(text=i18n.button.settings_reminder(), callback_data="settings:reminder")],
        [InlineKeyboardButton(text=i18n.button.settings_tz(), callback_data="settings:tz")],
        [InlineKeyboardButton(text=i18n.button.settings_pos(), callback_data="settings:pos")],
    ])


def parts_of_speech_kb(i18n, mask: int) -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(
        text=("✅ " if mask & POS_BITS[pos] else "▫️ ") + i18n.get("pos-" + pos),
        callback_data="pos:toggle:" + pos,
    ) for pos in PARTS_OF_SPEECH]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=("✅ " if mask == ALL_POS else "") + i18n.button.pos_all(),
                              callback_data="pos:all")],
        *[buttons[index:index + 2] for index in range(0, len(buttons), 2)],
        [InlineKeyboardButton(text=i18n.button.pos_done(), callback_data="pos:done")],
    ])
