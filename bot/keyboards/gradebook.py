from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def kb_progress_filters():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Фильтр: тренинг", callback_data="gb:filter:training"),
        InlineKeyboardButton("Фильтр: урок", callback_data="gb:filter:lesson"),
    )
    kb.add(
        InlineKeyboardButton("Статус: вовремя", callback_data="gb:status:on_time"),
        InlineKeyboardButton("Статус: не вовремя", callback_data="gb:status:not_on_time"),
    )
    return kb
