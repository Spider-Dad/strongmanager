import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher.filters import IDFilter
from bot.utils.alerts import ErrorCollector
from bot.utils.markdown import bold, escape_markdown_v2
from datetime import datetime

logger = logging.getLogger(__name__)

# Глобальный коллектор ошибок
error_collector = ErrorCollector(max_errors=20)

# Обработчик команды /stats для администраторов
async def cmd_stats(message: types.Message, config):
    # Здесь будет логика сбора статистики по использованию бота
    await message.answer(
        f"📊 {bold('Статистика использования бота')}\n\n"
        f"Функция находится в разработке\\."
    )

# Обработчик команды /broadcast для рассылки всем пользователям
async def cmd_broadcast(message: types.Message, config):
    # Здесь будет логика для массовой рассылки
    await message.answer(
        f"📣 {bold('Массовая рассылка')}\n\n"
        f"Функция находится в разработке\\."
    )

# Обработчик команды /alerts для управления алертами
async def cmd_alerts(message: types.Message, config):
    """Показывает меню управления алертами"""
    # Отладочная информация
    logger.info(f"Команда /alerts от пользователя {message.from_user.id} ({message.from_user.username})")
    logger.info(f"Список администраторов: {config.admin_ids}")
    logger.info(f"Является ли пользователь администратором: {message.from_user.id in config.admin_ids}")

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("📊 Последние ошибки", callback_data="alerts_errors"),
        types.InlineKeyboardButton("🔔 Тест алерта", callback_data="alerts_test"),
        types.InlineKeyboardButton("ℹ️ Статус системы", callback_data="alerts_status")
    )

    await message.answer(
        f"🚨 {bold('Управление системой алертов')}\n\n"
        f"Выберите действие:",
        reply_markup=keyboard
    )

# Обработчик для просмотра последних ошибок
async def callback_alerts_errors(callback_query: types.CallbackQuery):
    """Показывает последние ошибки"""
    summary = error_collector.get_summary()

    # Экранируем специальные символы для MarkdownV2
    summary_escaped = escape_markdown_v2(summary)

    await callback_query.message.edit_text(
        f"📊 {bold('Последние ошибки')}\n\n{summary_escaped}",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("◀️ Назад", callback_data="alerts_menu")
        )
    )
    await callback_query.answer()

# Обработчик для теста алертов
async def callback_alerts_test(callback_query: types.CallbackQuery):
    """Генерирует тестовую ошибку для проверки системы алертов"""
    try:
        # Генерируем тестовую ошибку
        logger.error("Тестовый алерт: Это тестовое сообщение для проверки системы алертов")

        # Также генерируем ошибку с трейсбеком
        raise ValueError("Тестовая ошибка с трейсбеком")
    except ValueError:
        logger.error("Тестовая ошибка с трейсбеком", exc_info=True)

    await callback_query.answer("✅ Тестовые алерты отправлены!", show_alert=True)

    # Возвращаемся в меню
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("📊 Последние ошибки", callback_data="alerts_errors"),
        types.InlineKeyboardButton("🔔 Тест алерта", callback_data="alerts_test"),
        types.InlineKeyboardButton("ℹ️ Статус системы", callback_data="alerts_status")
    )

    await callback_query.message.edit_text(
        f"🚨 {bold('Управление системой алертов')}\n\n"
        f"Тестовые алерты отправлены\\. Проверьте личные сообщения\\.",
        reply_markup=keyboard
    )

# Обработчик для статуса системы
async def callback_alerts_status(callback_query: types.CallbackQuery, config):
    """Показывает статус системы алертов"""
    status_text = (
        f"ℹ️ {bold('Статус системы алертов')}\n\n"
        f"✅ Система алертов: {'Активна' if config.admin_ids else 'Отключена'}\n"
        f"👥 Администраторы: {len(config.admin_ids)}\n"
        f"📊 Ошибок в буфере: {len(error_collector.errors)}\n"
        f"🕐 Текущее время: {escape_markdown_v2(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}"
    )

    await callback_query.message.edit_text(
        status_text,
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("◀️ Назад", callback_data="alerts_menu")
        )
    )
    await callback_query.answer()

# Обработчик для возврата в меню алертов
async def callback_alerts_menu(callback_query: types.CallbackQuery):
    """Возвращает в главное меню алертов"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("📊 Последние ошибки", callback_data="alerts_errors"),
        types.InlineKeyboardButton("🔔 Тест алерта", callback_data="alerts_test"),
        types.InlineKeyboardButton("ℹ️ Статус системы", callback_data="alerts_status")
    )

    await callback_query.message.edit_text(
        f"🚨 {bold('Управление системой алертов')}\n\n"
        f"Выберите действие:",
        reply_markup=keyboard
    )
    await callback_query.answer()

def register_admin_handlers(dp: Dispatcher, config):
    """
    Регистрирует обработчики для администраторов.

    Args:
        dp: Диспетчер бота
        config: Конфигурация бота
    """
    # Фильтр по ID администраторов
    admin_filter = IDFilter(user_id=config.admin_ids)

    dp.register_message_handler(
        lambda msg: cmd_stats(msg, config),
        admin_filter,
        commands=["stats"],
        state="*"
    )
    dp.register_message_handler(
        lambda msg: cmd_broadcast(msg, config),
        admin_filter,
        commands=["broadcast"],
        state="*"
    )

    # Регистрация команды /alerts
    dp.register_message_handler(
        lambda msg: cmd_alerts(msg, config),
        admin_filter,
        commands=["alerts"],
        state="*"
    )

    # Регистрация callback-обработчиков для алертов
    dp.register_callback_query_handler(
        callback_alerts_errors,
        admin_filter,
        lambda c: c.data == "alerts_errors",
        state="*"
    )

    dp.register_callback_query_handler(
        callback_alerts_test,
        admin_filter,
        lambda c: c.data == "alerts_test",
        state="*"
    )

    dp.register_callback_query_handler(
        lambda c: callback_alerts_status(c, config),
        admin_filter,
        lambda c: c.data == "alerts_status",
        state="*"
    )

    dp.register_callback_query_handler(
        callback_alerts_menu,
        admin_filter,
        lambda c: c.data == "alerts_menu",
        state="*"
    )
