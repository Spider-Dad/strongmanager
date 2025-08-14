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


def kb_training_select(options: list[tuple[int, str]], has_more: bool = False):
    kb = InlineKeyboardMarkup(row_width=1)
    for tr_id, title in options:
        title_short = title if len(title) <= 48 else title[:45] + "…"
        kb.add(InlineKeyboardButton(f"📘 {title_short}", callback_data=f"gb:set:tr:{tr_id}"))
    if has_more:
        kb.add(InlineKeyboardButton("Показаны первые 10", callback_data="gb:nop"))
    kb.add(InlineKeyboardButton("← Назад", callback_data="gb:back"))
    return kb


def kb_pagination(page: int, total_pages: int, base_cb: str) -> InlineKeyboardMarkup:
    """Построение клавиатуры пагинации.

    base_cb: префикс callback, например "gb:page:tr:12:lesson:100". Мы добавим ":p:{page}" в конец.
    """
    kb = InlineKeyboardMarkup(row_width=3)
    prev_page = max(1, page - 1)
    next_page = min(total_pages, page + 1)
    kb.add(
        InlineKeyboardButton("←", callback_data=f"{base_cb}:p:{prev_page}"),
        InlineKeyboardButton(f"{page}/{total_pages}", callback_data="gb:nop"),
        InlineKeyboardButton("→", callback_data=f"{base_cb}:p:{next_page}"),
    )
    kb.add(InlineKeyboardButton("← Назад", callback_data="gb:back"))
    return kb
