from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def onboarding_kb(i18n) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=i18n.button.start_zero(), callback_data="onboard:zero")],
        [InlineKeyboardButton(text=i18n.button.start_skip(), callback_data="onboard:skip")],
    ])


def answer_actions_kb(i18n, word_id_hex: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=i18n.button.skip(), callback_data=f"card:skip:{word_id_hex}"
            ),
            InlineKeyboardButton(
                text=i18n.button.hard(), callback_data=f"card:hard:{word_id_hex}"
            ),
        ],
    ])


def settings_kb(i18n) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=i18n.button.settings_batch(), callback_data="settings:batch")],
        [InlineKeyboardButton(text=i18n.button.settings_reminder(), callback_data="settings:reminder")],
        [InlineKeyboardButton(text=i18n.button.settings_tz(), callback_data="settings:tz")],
    ])
