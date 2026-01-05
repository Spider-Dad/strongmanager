from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import Optional


def kb_progress_filters():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Фильтр по урокам", callback_data="gb:filter:lesson"),
        InlineKeyboardButton("Сбросить фильтр", callback_data="gb:back"),
    )
    return kb


def kb_training_select(options: list[tuple[int, str]], has_more: bool = False):
    kb = InlineKeyboardMarkup(row_width=1)
    for tr_id, title in options:
        title_short = title if len(title) <= 48 else title[:45] + "…"
        kb.add(InlineKeyboardButton(title_short, callback_data=f"gb:set:tr:{tr_id}"))
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


def kb_filters_with_pagination(training_id: Optional[int], lesson_id: Optional[int], page: int, total_pages: int, base_cb: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    # Pagination row наверх - в одном ряду
    prev_page = max(1, page - 1)
    next_page = min(total_pages, page + 1)
    kb.row(
        InlineKeyboardButton("←", callback_data=f"{base_cb}:p:{prev_page}"),
        InlineKeyboardButton(f"{page}/{total_pages}", callback_data="gb:nop"),
        InlineKeyboardButton("→", callback_data=f"{base_cb}:p:{next_page}"),
    )
    # Filters row под пагинацией - на одной строке
    lesson_btn_text = "Сменить урок" if lesson_id else "Фильтр по урокам"
    kb.row(
        InlineKeyboardButton(lesson_btn_text, callback_data="gb:filter:lesson"),
        InlineKeyboardButton("Сбросить фильтр", callback_data="gb:back"),
    )
    return kb


def kb_training_select_with_status(options: list[tuple[int, str, bool]], has_more: bool = False):
    """options: [(training_id, title_with_state, allowed)]"""
    kb = InlineKeyboardMarkup(row_width=1)
    for tr_id, title, allowed in options:
        title_short = title if len(title) <= 48 else title[:45] + "…"
        cb = f"gb:set:tr:{tr_id}" if allowed else "gb:block:not_started"
        kb.add(InlineKeyboardButton(title_short, callback_data=cb))
    if has_more:
        kb.add(InlineKeyboardButton("Показаны первые 10", callback_data="gb:nop"))
    kb.add(InlineKeyboardButton("← Назад", callback_data="gb:back"))
    return kb


def kb_lesson_select_with_status(options: list[tuple[int, str, bool]], training_id: int, has_more: bool = False):
    kb = InlineKeyboardMarkup(row_width=1)
    for lesson_id, title, allowed in options:
        title_short = title if len(title) <= 48 else title[:45] + "…"
        cb = (f"gb:set:lesson:{lesson_id}:tr:{training_id}" if allowed else "gb:block:not_started")
        kb.add(InlineKeyboardButton(title_short, callback_data=cb))
    if has_more:
        kb.add(InlineKeyboardButton("Показаны первые 10", callback_data="gb:nop"))
    kb.add(InlineKeyboardButton("← Назад", callback_data="gb:back"))
    return kb


def _kb_lesson_select_with_pagination(options: list[tuple[int, str, bool]], training_id: Optional[int], page: int, total_pages: int):
    """Создает клавиатуру для выбора урока с пагинацией. training_id оставлен для совместимости."""
    kb = InlineKeyboardMarkup(row_width=1)

    # Добавляем кнопки уроков
    for lesson_id, title, allowed in options:
        title_short = title if len(title) <= 48 else title[:45] + "…"
        # Поддерживаем старый формат с training_id для совместимости
        if training_id is not None:
            cb = (f"gb:set:lesson:{lesson_id}:tr:{training_id}" if allowed else "gb:block:not_started")
        else:
            cb = (f"gb:set:lesson:{lesson_id}" if allowed else "gb:block:not_started")
        kb.add(InlineKeyboardButton(title_short, callback_data=cb))

    # Добавляем пагинацию, если есть больше одной страницы
    if total_pages > 1:
        prev_page = max(1, page - 1)
        next_page = min(total_pages, page + 1)
        base_cb = "gb:page:lessons"

        kb.row(
            InlineKeyboardButton("←", callback_data=f"{base_cb}:p:{prev_page}"),
            InlineKeyboardButton(f"{page}/{total_pages}", callback_data="gb:nop"),
            InlineKeyboardButton("→", callback_data=f"{base_cb}:p:{next_page}"),
        )

    kb.add(InlineKeyboardButton("← Назад", callback_data="gb:back"))
    return kb