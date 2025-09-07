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
    # Добавлена точка (.) в список специальных символов для корректного экранирования
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


def convert_pseudo_markdown_to_v2(text: str) -> str:
    """
    Конвертирует псевдо-markdown (с простыми * для жирного текста) в правильный MarkdownV2.

    Args:
        text: Исходный текст с псевдо-markdown

    Returns:
        Текст в формате MarkdownV2
    """
    import re

    # Сначала обрабатываем ссылки, чтобы не трогать их содержимое
    links = []
    link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'

    def save_link(match):
        link_text = match.group(1).replace('*', '')  # Убираем звездочки из текста ссылки
        url = match.group(2)
        placeholder = f"LINKPLACEHOLDER{len(links)}"
        links.append(f'[{escape_markdown_v2(link_text)}]({url})')
        return placeholder

    # Заменяем ссылки на плейсхолдеры
    text = re.sub(link_pattern, save_link, text)

    # Теперь обрабатываем жирный текст
    # Ищем текст между звездочками
    bold_pattern = r'\*([^*]+)\*'

    def replace_bold(match):
        bold_text = match.group(1)
        return f'*{escape_markdown_v2(bold_text)}*'

    # Заменяем жирный текст
    text = re.sub(bold_pattern, replace_bold, text)

    # Экранируем остальные специальные символы, но НЕ звездочки от жирного текста
    # Разделяем текст на части, чтобы не трогать уже обработанный markdown

    # Находим все позиции жирного текста и плейсхолдеров ссылок
    protected_positions = []
    for match in re.finditer(r'\*[^*]+\*', text):
        protected_positions.append((match.start(), match.end()))

    for match in re.finditer(r'LINKPLACEHOLDER\d+', text):
        protected_positions.append((match.start(), match.end()))

    # Сортируем позиции по порядку
    protected_positions.sort()

    # Обрабатываем текст по частям
    result = ""
    last_pos = 0

    for start, end in protected_positions:
        # Обрабатываем текст перед защищенной областью
        before_protected = text[last_pos:start]
        result += escape_markdown_v2(before_protected)

        # Добавляем защищенную область как есть
        result += text[start:end]

        last_pos = end

    # Обрабатываем оставшийся текст
    if last_pos < len(text):
        result += escape_markdown_v2(text[last_pos:])

    # Восстанавливаем ссылки
    for i, link in enumerate(links):
        result = result.replace(f"LINKPLACEHOLDER{i}", link)

    return result