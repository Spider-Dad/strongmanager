import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher.filters import IDFilter
from bot.utils.alerts import ErrorCollector
from bot.utils.markdown import bold, escape_markdown_v2
from datetime import datetime, timedelta
from bot.services.sync_service import SyncService
from sqlalchemy import select, func
import bot.services.database as db

logger = logging.getLogger(__name__)

# Глобальный коллектор ошибок
error_collector = ErrorCollector(max_errors=20)

# Глобальный сервис синхронизации
sync_service = None

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

# Обработчик команды /sync для управления синхронизацией БД
async def cmd_sync(message: types.Message, config):
    """Показывает меню управления синхронизацией БД"""
    logger.info(f"Команда /sync от пользователя {message.from_user.id} ({message.from_user.username})")

    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("🔄 Синхронизировать сейчас", callback_data="sync_now"),
        types.InlineKeyboardButton("📊 Статус синхронизации", callback_data="sync_status"),
        types.InlineKeyboardButton("⚙️ Настройки", callback_data="sync_settings")
    )

    await message.answer(
        f"🗄️ {bold('Управление синхронизацией БД')}\n\n"
        f"Синхронизация данных из Google Sheets в SQLite\\.\n"
        f"Выберите действие:",
        reply_markup=keyboard,
        parse_mode='MarkdownV2'
    )

# Обработчик для запуска синхронизации
async def callback_sync_now(callback_query: types.CallbackQuery):
    """Запускает синхронизацию БД"""
    global sync_service

    if sync_service.is_syncing:
        await callback_query.answer("⏳ Синхронизация уже выполняется!", show_alert=True)
        return

    await callback_query.answer("🔄 Запускаю синхронизацию...")

    # Обновляем сообщение
    await callback_query.message.edit_text(
        f"🔄 {bold('Синхронизация запущена')}\n\n"
        f"⏳ Пожалуйста, подождите\\.\\.\\.\n"
        f"Это может занять несколько минут\\.",
        parse_mode='MarkdownV2'
    )

    # Запускаем синхронизацию
    result = await sync_service.sync_database()

    # Формируем отчет о синхронизации
    if result['success']:
        records_text = "\n".join([
            f"• {table}: {count} записей"
            for table, count in result['records_synced'].items()
        ])

        message_text = (
            f"✅ {bold('Синхронизация завершена успешно')}\n\n"
            f"⏱️ Время выполнения: {result['duration']} сек\\.\n\n"
            f"{bold('Синхронизировано:')}\n{escape_markdown_v2(records_text)}"
        )
    else:
        message_text = (
            f"❌ {bold('Ошибка синхронизации')}\n\n"
            f"{escape_markdown_v2(result.get('error', 'Неизвестная ошибка'))}\n"
            f"Смотрите логи приложения"
        )

    # Кнопка назад в меню синхронизации
    keyboard = types.InlineKeyboardMarkup(row_width=1).add(
        types.InlineKeyboardButton("◀️ Назад", callback_data="sync_menu")
    )

    await callback_query.message.edit_text(
        message_text,
        reply_markup=keyboard,
        parse_mode='MarkdownV2'
    )

# Обработчик для просмотра статуса синхронизации
async def callback_sync_status(callback_query: types.CallbackQuery):
    """Показывает статус последней синхронизации"""
    global sync_service

    status = await sync_service.get_sync_status()

    if status.get('error'):
        message_text = (
            f"❌ {bold('Ошибка получения статуса')}\n\n"
            f"{escape_markdown_v2(status['error'])}"
        )
    elif status['status'] == 'never':
        message_text = (
            f"ℹ️ {bold('Статус синхронизации')}\n\n"
            f"📊 Синхронизация еще не выполнялась\n"
            f"🔄 Автосинхронизация: {'Включена' if status['auto_sync_enabled'] else 'Отключена'}"
        )
    else:
        # Форматируем дату
        last_sync_date = status['last_sync_date']
        if isinstance(last_sync_date, str):
            try:
                last_sync_date = datetime.fromisoformat(last_sync_date.replace('Z', '+00:00'))
            except:
                pass

        date_str = last_sync_date.strftime('%d\\.%m\\.%Y %H:%M:%S') if isinstance(last_sync_date, datetime) else str(last_sync_date)

        message_text = (
            f"ℹ️ {bold('Статус синхронизации')}\n\n"
            f"📅 Последняя синхронизация: {date_str}\n"
            f"{'✅' if status['status'] == 'success' else '❌'} Статус: {status['status']}\n"
        )

        if status['duration_seconds']:
            message_text += f"⏱️ Длительность: {status['duration_seconds']} сек\\.\n"

        if status.get('records_synced'):
            records_text = "\n".join([
                f"  • {table}: {count}"
                for table, count in status['records_synced'].items()
            ])
            message_text += f"\n{bold('Синхронизировано записей:')}\n{escape_markdown_v2(records_text)}\n"

        if status.get('error_message'):
            message_text += f"\n❌ Ошибка: {escape_markdown_v2(status['error_message'])}\n"

        message_text += f"\n🔄 Автосинхронизация: {'Включена' if status['auto_sync_enabled'] else 'Отключена'}"
        if status['auto_sync_enabled']:
            try:
                next_time = None
                if isinstance(last_sync_date, datetime):
                    next_time = last_sync_date + timedelta(minutes=status['sync_interval_minutes'])
                if next_time:
                    next_time_str = next_time.strftime('%d\\.%m\\.%Y %H:%M:%S')
                    message_text += f"\n📅 Следующая синхронизация: {next_time_str}"
            except Exception:
                pass

        if status['is_syncing']:
            message_text += f"\n\n⏳ {bold('Синхронизация выполняется сейчас!')}"

    await callback_query.message.edit_text(
        message_text,
        reply_markup=types.InlineKeyboardMarkup(row_width=1).add(
            types.InlineKeyboardButton("◀️ Назад", callback_data="sync_menu")
        ),
        parse_mode='MarkdownV2'
    )
    await callback_query.answer()

# Обработчик для настроек синхронизации
async def callback_sync_settings(callback_query: types.CallbackQuery):
    """Показывает настройки синхронизации"""
    global sync_service

    status = await sync_service.get_sync_status()

    message_text = (
        f"⚙️ {bold('Настройки синхронизации')}\n\n"
        f"🔄 Автосинхронизация: {'Включена' if status['auto_sync_enabled'] else 'Отключена'}\n"
    )

    if status['auto_sync_enabled']:
        message_text += f"⏱️ Интервал: каждые {status['sync_interval_minutes']} минут\n"

    message_text += (
        f"\n{bold('Переменные окружения:')}\n"
        f"• SYNC\\_INTERVAL\\_MINUTES \\- интервал автосинхронизации в минутах\n"
        f"  \\(0 \\= отключена\\)\n\n"
        f"ℹ️ Для изменения интервала необходимо изменить значение переменной окружения и перузапустить бота на сервере\\."
    )

    await callback_query.message.edit_text(
        message_text,
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("◀️ Назад", callback_data="sync_menu")
        )
    )
    await callback_query.answer()

# Обработчик для возврата в меню синхронизации
async def callback_sync_menu(callback_query: types.CallbackQuery):
    """Возвращает в главное меню синхронизации"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("🔄 Синхронизировать сейчас", callback_data="sync_now"),
        types.InlineKeyboardButton("📊 Статус синхронизации", callback_data="sync_status"),
        types.InlineKeyboardButton("⚙️ Настройки", callback_data="sync_settings")
    )

    await callback_query.message.edit_text(
        f"🗄️ {bold('Управление синхронизацией БД')}\n\n"
        f"Синхронизация данных из Google Sheets в SQLite\\.\n"
        f"Выберите действие:",
        reply_markup=keyboard,
        parse_mode='MarkdownV2'
    )
    await callback_query.answer()

def register_admin_handlers(dp: Dispatcher, config):
    """
    Регистрирует обработчики для администраторов.

    Args:
        dp: Диспетчер бота
        config: Конфигурация бота
    """
    # Инициализируем сервис синхронизации
    global sync_service
    sync_service = SyncService(config)

    # Фильтр по ID администраторов
    admin_filter = IDFilter(user_id=config.admin_ids)

    # Регистрация команды /alerts
    dp.register_message_handler(
        lambda msg: cmd_alerts(msg, config),
        admin_filter,
        commands=["alerts"],
        state="*"
    )

    # Регистрация команды /sync
    dp.register_message_handler(
        lambda msg: cmd_sync(msg, config),
        admin_filter,
        commands=["sync"],
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


    # Регистрация callback-обработчиков для синхронизации
    dp.register_callback_query_handler(
        callback_sync_now,
        admin_filter,
        lambda c: c.data == "sync_now",
        state="*"
    )

    dp.register_callback_query_handler(
        callback_sync_status,
        admin_filter,
        lambda c: c.data == "sync_status",
        state="*"
    )

    dp.register_callback_query_handler(
        callback_sync_settings,
        admin_filter,
        lambda c: c.data == "sync_settings",
        state="*"
    )

    dp.register_callback_query_handler(
        callback_sync_menu,
        admin_filter,
        lambda c: c.data == "sync_menu",
        state="*"
    )
