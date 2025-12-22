import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher.filters import IDFilter
from bot.utils.alerts import ErrorCollector
from bot.utils.markdown import bold, escape_markdown_v2
from datetime import datetime, timedelta
from sqlalchemy import select, func
import bot.services.database as db

logger = logging.getLogger(__name__)

# Глобальный коллектор ошибок
error_collector = ErrorCollector(max_errors=20)

# Обработчик команды /alerts для управления алертами
async def cmd_alerts(message: types.Message, config):
    """Показывает меню управления алертами"""
    # Отладочная информация
    logger.info(f"Команда /alerts от пользователя {message.from_user.id} ({message.from_user.username})")
    logger.info(f"Список администраторов: {config.admin_ids}")
    logger.info(f"Является ли пользователь администратором: {message.from_user.id in config.admin_ids}")

    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("📊 Последние ошибки", callback_data="alerts_errors"),
        types.InlineKeyboardButton("ℹ️ Статус системы", callback_data="alerts_status"),
    )

    await message.answer(
        f"🚨 {bold('Управление системой алертов')}\n\n"
        f"Выберите действие:",
        reply_markup=keyboard,
        parse_mode='MarkdownV2'
    )

# Обработчик для просмотра последних ошибок (за последние 24 часа, только ERROR, максимум 3)
async def callback_alerts_errors(callback_query: types.CallbackQuery):
    cutoff = datetime.now() - timedelta(days=1)

    async with db.async_session() as session:
        result = await session.execute(
            select(db.ErrorLog)
            .where(
                db.ErrorLog.level.in_(["ERROR", "CRITICAL"]),
                db.ErrorLog.timestamp >= cutoff,
            )
            .order_by(db.ErrorLog.timestamp.desc())
            .limit(3)
        )
        errors = result.scalars().all()

    if not errors:
        body = (
            "Последние ошибки бота с типом ERROR, CRITICAL\n\n"
            "за последние сутки не зафиксированы ошибки"
        )
    else:
        lines = [
            "Последние ошибки бота с типом ERROR, CRITICAL",
            "",
        ]
        for err in errors:
            ts = err.timestamp.strftime('%Y-%m-%d %H:%M:%S') if err.timestamp else ""
            module = (err.module or err.logger_name or "unknown")
            level = (err.level or "").upper()
            message = (err.message or "")[:500]
            lines.append(f"{level} {ts} — {module}")
            lines.append(f"{message}")
            lines.append("")
        body = "\n".join(lines).rstrip()

    await callback_alerts_menu_render(
        callback_query,
        title=f"📊 {bold('Последние ошибки')}\n\n",
        body=body,
    )

# Удалён обработчик теста алертов — отправка алертов администраторам отключена

# Обработчик для статуса системы
async def callback_alerts_status(callback_query: types.CallbackQuery, config):
    """Показывает краткую статистику по ошибкам за последние сутки (CRITICAL, ERROR, WARNING) по модулям"""
    cutoff = datetime.now() - timedelta(days=1)

    async with db.async_session() as session:
        result = await session.execute(
            select(
                db.ErrorLog.module,
                db.ErrorLog.level,
                func.count().label("cnt"),
            )
            .where(
                db.ErrorLog.timestamp >= cutoff,
                db.ErrorLog.level.in_(["CRITICAL", "ERROR", "WARNING"]),
            )
            .group_by(db.ErrorLog.module, db.ErrorLog.level)
        )
        rows = result.all()

    if not rows:
        body = (
            "Количество ошибок по типам в модулях:\n\n"
            "за последние сутки не зафиксированы ошибки с типом CRITICAL, ERROR, WARNING"
        )
    else:
        # Собираем статистику: модуль -> {level: count}
        stats = {}
        for module, level, cnt in rows:
            key = module or "unknown"
            if key not in stats:
                stats[key] = {"CRITICAL": 0, "ERROR": 0, "WARNING": 0}
            stats[key][level] = cnt

        lines = [
            "Количество ошибок по типам в модулях:",
            "",
        ]
        for module, level_counts in sorted(stats.items()):
            lines.append(f"{module}:")
            lines.append(
                f"CRITICAL: {level_counts['CRITICAL']}, ERROR: {level_counts['ERROR']}, WARNING: {level_counts['WARNING']}"
            )
            lines.append("")
        body = "\n".join(lines).rstrip()

    await callback_alerts_menu_render(
        callback_query,
        title=f"ℹ️ {bold('Статус системы за последние сутки')}\n\n",
        body=body,
    )

# Обработчик для возврата в меню алертов
async def callback_alerts_menu(callback_query: types.CallbackQuery):
    """Возвращает в главное меню алертов"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("📊 Последние ошибки", callback_data="alerts_errors"),
        types.InlineKeyboardButton("ℹ️ Статус системы", callback_data="alerts_status")
    )

    await callback_query.message.edit_text(
        f"🚨 {bold('Управление системой алертов')}\n\n"
        f"Выберите действие:",
        reply_markup=keyboard,
        parse_mode='MarkdownV2'
    )
    await callback_query.answer()

async def callback_alerts_menu_render(callback_query: types.CallbackQuery, title: str, body: str):
    keyboard = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("◀️ Назад", callback_data="alerts_menu")
    )
    await callback_query.message.edit_text(
        f"{title}{escape_markdown_v2(body)}",
        reply_markup=keyboard,
        parse_mode='MarkdownV2'
    )
    await callback_query.answer()

# Удалён обработчик диагностики Google Script — вне требований текущей задачи

# УДАЛЕНО: Команда /sync - синхронизация с Google Sheets больше не используется
# После миграции на PostgreSQL все данные управляются напрямую через DBeaver

# УДАЛЕНО: Все функции синхронизации с Google Sheets
# После миграции на PostgreSQL синхронизация не используется
# Справочные данные обновляются напрямую через DBeaver

def register_admin_handlers(dp: Dispatcher, config):
    """
    Регистрирует обработчики для администраторов.

    Args:
        dp: Диспетчер бота
        config: Конфигурация бота
    """
    # Фильтр по ID администраторов
    admin_filter = IDFilter(user_id=config.admin_ids)

    # Регистрация команды /alerts
    dp.register_message_handler(
        lambda msg: cmd_alerts(msg, config),
        admin_filter,
        commands=["alerts"],
        state="*"
    )

    # УДАЛЕНО: Регистрация команды /sync
    # Синхронизация с Google Sheets больше не используется

    # Регистрация callback-обработчиков для алертов
    dp.register_callback_query_handler(
        callback_alerts_errors,
        admin_filter,
        lambda c: c.data == "alerts_errors",
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

    # УДАЛЕНО: Регистрация callback-обработчиков для синхронизации
    # Все функции синхронизации с Google Sheets удалены
