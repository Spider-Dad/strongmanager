"""
Утилиты для работы с MarkdownV2 форматированием в Telegram.
"""

import re
from typing import Optional


def escape_markdown_v2(text: str) -> str:
    """
    Экранирует специальные символы для MarkdownV2.

    Args:
        text: Исходный текст

    Returns:
        Экранированный текст
    """
    # Символы, которые нужно экранировать в MarkdownV2
    special_chars = r'_*[]()~`>#+-=|{}.!'

    # Экранируем каждый специальный символ
    for char in special_chars:
        text = text.replace(char, f'\\{char}')

    return text


def bold(text: str) -> str:
    """
    Делает текст жирным в MarkdownV2.

    Args:
        text: Текст для форматирования

    Returns:
        Отформатированный текст
    """
    return f'*{escape_markdown_v2(text)}*'


def italic(text: str) -> str:
    """
    Делает текст курсивом в MarkdownV2.

    Args:
        text: Текст для форматирования

    Returns:
        Отформатированный текст
    """
    return f'_{escape_markdown_v2(text)}_'


def code(text: str) -> str:
    """
    Форматирует текст как код в MarkdownV2.

    Args:
        text: Текст для форматирования

    Returns:
        Отформатированный текст
    """
    return f'`{text}`'


def code_block(text: str, language: Optional[str] = None) -> str:
    """
    Форматирует текст как блок кода в MarkdownV2.

    Args:
        text: Текст для форматирования
        language: Язык программирования (опционально)

    Returns:
        Отформатированный текст
    """
    if language:
        return f'```{language}\n{text}\n```'
    return f'```\n{text}\n```'


def link(text: str, url: str) -> str:
    """
    Создает ссылку в MarkdownV2.

    Args:
        text: Текст ссылки
        url: URL ссылки

    Returns:
        Отформатированная ссылка
    """
    return f'[{escape_markdown_v2(text)}]({url})'


def hidden_link(url: str) -> str:
    """
    Создает скрытую ссылку в MarkdownV2.

    Args:
        url: URL ссылки

    Returns:
        Скрытая ссылка
    """
    return f'[​]({url})'


def strikethrough(text: str) -> str:
    """
    Зачеркивает текст в MarkdownV2.

    Args:
        text: Текст для форматирования

    Returns:
        Отформатированный текст
    """
    return f'~{escape_markdown_v2(text)}~'


def underline(text: str) -> str:
    """
    Подчеркивает текст в MarkdownV2.

    Args:
        text: Текст для форматирования

    Returns:
        Отформатированный текст
    """
    return f'__{escape_markdown_v2(text)}__'


def spoiler(text: str) -> str:
    """
    Создает спойлер в MarkdownV2.

    Args:
        text: Текст для скрытия

    Returns:
        Отформатированный спойлер
    """
    return f'||{escape_markdown_v2(text)}||'


def format_notification(title: str, message: str, url: Optional[str] = None) -> str:
    """
    Форматирует уведомление с использованием MarkdownV2.

    Args:
        title: Заголовок уведомления
        message: Текст сообщения
        url: Ссылка (опционально)

    Returns:
        Отформатированное уведомление
    """
    formatted_text = f"{bold(title)}\n\n{escape_markdown_v2(message)}"

    if url:
        formatted_text += f"\n\n{link('Перейти к заданию', url)}"

    return formatted_text


def format_student_action(student_name: str, action: str, task_name: str, url: Optional[str] = None) -> str:
    """
    Форматирует уведомление о действии студента.

    Args:
        student_name: Имя студента
        action: Действие (например, "отправил ответ", "оставил комментарий")
        task_name: Название задания
        url: Ссылка на задание (опционально)

    Returns:
        Отформатированное уведомление
    """
    text = f"👤 Студент {bold(student_name)} {escape_markdown_v2(action)}\n"
    text += f"📝 Задание: {italic(task_name)}"

    if url:
        text += f"\n\n{link('Посмотреть задание', url)}"

    return text