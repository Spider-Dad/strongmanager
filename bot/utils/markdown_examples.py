"""
Примеры использования MarkdownV2 разметки в Telegram боте.
"""

from bot.utils.markdown import (
    bold, italic, code, code_block, link, hidden_link,
    strikethrough, underline, spoiler, escape_markdown_v2,
    format_notification, format_student_action
)

def get_markdown_examples():
    """
    Возвращает примеры различных типов форматирования.

    Returns:
        Dict: Словарь с примерами
    """
    examples = {
        "basic_formatting": {
            "bold": bold("Жирный текст"),
            "italic": italic("Курсивный текст"),
            "code": code("код"),
            "strikethrough": strikethrough("Зачеркнутый текст"),
            "underline": underline("Подчеркнутый текст"),
            "spoiler": spoiler("Скрытый текст")
        },

        "links": {
            "regular_link": link("Ссылка на Google", "https://google.com"),
            "hidden_link": hidden_link("https://example.com")
        },

        "code_blocks": {
            "simple_code_block": code_block("print('Hello, World!')"),
            "python_code_block": code_block("def hello():\n    print('Hello!')", "python")
        },

        "notifications": {
            "student_answer": format_student_action(
                "Иван Петров",
                "отправил ответ на задание",
                "Урок 1: Основы менеджмента",
                "https://example.com/task/123"
            ),
            "student_comment": format_student_action(
                "Мария Сидорова",
                "оставил комментарий к заданию",
                "Урок 2: Планирование"
            ),
            "deadline_notification": format_notification(
                "⏰ Приближается дедлайн",
                "Задание: Урок 3: Контроль\nДедлайн: 25.12.2024 23:59",
                "https://example.com/task/456"
            )
        },

        "complex_message": (
            f"{bold('📚 Новое уведомление')}\n\n"
            f"Студент {italic('Анна Козлова')} отправила ответ на задание:\n"
            f"{code('Урок 4: Мотивация персонала')}\n\n"
            f"Комментарий: {escape_markdown_v2('Выполнила все пункты задания!')}\n\n"
            f"{link('Посмотреть ответ', 'https://example.com/answer/789')}"
        )
    }

    return examples

def get_special_characters_guide():
    """
    Возвращает руководство по экранированию специальных символов.

    Returns:
        str: Руководство по экранированию
    """
    guide = f"""
{bold('Специальные символы в MarkdownV2:')}

Следующие символы должны быть экранированы обратным слешем \\:
{code('_*[]()~`>#+-=|{}.!')}

{bold('Примеры экранирования:')}
• Точка: {escape_markdown_v2('Конец предложения.')}
• Восклицательный знак: {escape_markdown_v2('Отлично!')}
• Скобки: {escape_markdown_v2('Пример (важно)')}
• Дефис: {escape_markdown_v2('Пункт-1')}

{bold('Автоматическое экранирование:')}
Используйте функцию {code('escape_markdown_v2()')} для автоматического экранирования текста.
"""
    return guide.strip()

def get_formatting_tips():
    """
    Возвращает советы по форматированию.

    Returns:
        str: Советы по форматированию
    """
    tips = f"""
{bold('💡 Советы по форматированию:')}

1️⃣ {bold('Используйте функции-помощники')}
   Вместо ручного форматирования используйте готовые функции из {code('bot.utils.markdown')}

2️⃣ {bold('Экранируйте пользовательский ввод')}
   Всегда используйте {code('escape_markdown_v2()')} для текста от пользователей

3️⃣ {bold('Тестируйте сообщения')}
   Проверяйте форматирование перед отправкой в продакшн

4️⃣ {bold('Используйте скрытые ссылки')}
   Для аналитики и отслеживания используйте {code('hidden_link()')}

5️⃣ {bold('Структурируйте сообщения')}
   Используйте заголовки, списки и разделители для лучшей читаемости
"""
    return tips.strip()

# Пример использования в коде:
if __name__ == "__main__":
    examples = get_markdown_examples()

    print("=== ПРИМЕРЫ ФОРМАТИРОВАНИЯ ===")
    for category, items in examples.items():
        print(f"\n{category.upper()}:")
        if isinstance(items, dict):
            for name, example in items.items():
                print(f"  {name}: {example}")
        else:
            print(f"  {items}")

    print("\n" + "="*50)
    print(get_special_characters_guide())

    print("\n" + "="*50)
    print(get_formatting_tips())