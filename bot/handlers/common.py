import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from bot.handlers.auth import Registration, check_auth
from bot.utils.markdown import bold, escape_markdown_v2

logger = logging.getLogger(__name__)

# Обработчик команды /start
async def cmd_start(message: types.Message, state: FSMContext, config):
    # Сначала сбрасываем любые существующие состояния
    await state.finish()

    user_id = message.from_user.id
    is_admin = user_id in config.admin_ids

    # Для администраторов показываем специальное приветствие
    if is_admin:
        await message.answer(
            f"👋 {bold('Добро пожаловать, администратор!')}\n\n"
            f"Вы имеете доступ к административным функциям бота\\.\n\n"
            f"{bold('Доступные команды:')}\n"
            f"/help \\- Показать справку\n"
            f"/alerts \\- Управление системой алертов\n"
            f"/sync \\- Синхронизация БД с Google Sheets\n"
            f"/status \\- Информация о вашем статусе"
        )
    else:
        # Проверяем, авторизован ли обычный пользователь
        is_authorized = await check_auth(user_id)

        if is_authorized:
            # Для авторизованных наставников
            welcome_text = "Добро пожаловать в бот-помощник наставника онлайн школы Strong Manager!"
            await message.answer(
                f"👋 {escape_markdown_v2(welcome_text)}\n\n"
                f"Здесь вы будете получать уведомления о действиях ваших студентов\\.\n\n"
                f"{bold('Доступные команды:')}\n"
                f"/help \\- Показать справку\n"
                f"/about \\- Информация о боте\n"
                f"/status \\- Проверить свой статус"
            )
        else:
            # Для неавторизованных пользователей
            await message.answer(
                "Здравствуйте\\! Для регистрации введите ваш email, который используется в онлайн школе для руководителей Strong Manager"
            )
            # Устанавливаем состояние ожидания email
            await Registration.waiting_for_email.set()

# Обработчик команды /help
async def cmd_help(message: types.Message, config):
    user_id = message.from_user.id
    is_admin = user_id in config.admin_ids

    if is_admin:
        # Справка для администраторов
        help_text = (
            f"📚 {bold('Справка администратора')}\n\n"
            f"{bold('Команды управления ботом:')}\n"
            f"/start \\- Главное меню\n"
            f"/help \\- Показать эту справку\n"
            f"/status \\- Информация о вашем статусе\n\n"
            f"{bold('Административные команды:')}\n"
            f"/alerts \\- Управление системой алертов\n"
            f"  • Просмотр последних ошибок бота\n"
            f"  • Тестирование системы алертов\n"
            f"  • Статус системы\n\n"
            f"/sync \\- Синхронизация БД с Google Sheets\n"
            f"  • Ручная синхронизация данных\n"
            f"  • Просмотр статуса синхронизации\n"
            f"  • Настройки автосинхронизации\n\n"
            f"{bold('О системе алертов:')}\n"
            f"Вы автоматически получаете уведомления об ошибках уровня ERROR\\.\n"
            f"Алерты отправляются не чаще раза в 5 минут для одинаковых ошибок\\.\n\n"
            f"{bold('О синхронизации БД:')}\n"
            f"Синхронизация обновляет локальную БД данными из Google Sheets\\.\n"
            f"Автосинхронизация настраивается через SYNC\\_INTERVAL\\_MINUTES\\."
        )
    else:
        # Проверяем, авторизован ли обычный пользователь
        is_authorized = await check_auth(user_id)

        if is_authorized:
            # Справка для наставников
            help_text = (
                f"📚 {bold('Справка по использованию бота')}\n\n"
                f"{bold('Основные команды:')}\n"
                f"/start \\- Перезапустить бота\n"
                f"/help \\- Показать эту справку\n"
                f"/about \\- Информация о боте\n"
                f"/status \\- Проверить свой статус\n\n"
                f"{bold('Как работает бот:')}\n"
                f"• Бот автоматически отправляет уведомления о действиях ваших студентов\n"
                f"• Вы получаете уведомления о новых ответах на задания\n"
                f"• Вы получаете напоминания о приближающихся дедлайнах\n\n"
                f"Никаких дополнительных действий от вас не требуется\\!"
            )
        else:
            help_text = (
                f"📚 {bold('Справка')}\n\n"
                f"Для начала работы с ботом необходимо авторизоваться\\.\n\n"
                f"Отправьте команду /start и следуйте инструкциям\\.\n"
                f"Вам потребуется ввести email, который используется в онлайн школе\\."
            )

    await message.answer(help_text)

# Обработчик команды /about
async def cmd_about(message: types.Message, config):
    user_id = message.from_user.id
    is_admin = user_id in config.admin_ids

    if is_admin:
        # Информация для администраторов
        await message.answer(
            f"📱 {bold('Административная панель бота Strong Manager')}\n\n"
            f"Версия: 1\\.1\\.1\n\n"
            f"{bold('Назначение:')}\n"
            f"Этот бот предназначен для автоматизации работы наставников онлайн школы\\.\n\n"
            f"{bold('Ваши функции как администратора:')}\n"
            f"• Мониторинг работы бота\n"
            f"• Получение алертов об ошибках\n"
            f"• Управление синхронизацией БД\n"
            f"• Просмотр истории синхронизаций\n\n"
            f"{bold('Техническая информация:')}\n"
            f"• Интеграция с Google Sheets API\n"
            f"• Автоматическая система алертов\n"
            f"• Синхронизация БД по расписанию\n"
            f"• Поддержка webhook и long polling\n"
        )
    else:
        # Информация для обычных пользователей
        bot_name = "Бот-помощник наставника онлайн школы Strong Manager"
        await message.answer(
            f"📱 {bold(bot_name)}\n\n"
            f"Этот бот предназначен для оперативного оповещения наставников о действиях студентов:\n"
            f"• Новые ответы на задания\n"
            f"• Приближающиеся дедлайны по ответам на задания\n\n"
            f"Бот работает автоматически и не требует от вас никаких действий\\.\n"
            f"Просто держите уведомления включенными\\!"
        )

# Обработчик команды /status для проверки статуса пользователя
async def cmd_status(message: types.Message, config):
    """Показывает статус текущего пользователя"""
    user_id = message.from_user.id
    username = message.from_user.username or "не указан"

    # Проверяем, является ли администратором
    is_admin = user_id in config.admin_ids

    if is_admin:
        # Статус для администратора
        status_text = (
            f"👤 {bold('Статус администратора')}\n\n"
            f"👑 Роль: Администратор\n"
            f"✅ Доступ: Полный\n\n"
            f"{bold('Активные функции:')}\n"
            f"• Система алертов: {'✅' if config.admin_ids else '❌'}\n"
            f"• Получение ошибок: {'✅' if config.admin_ids else '❌'}\n"
            f"• Административные команды: {'✅' if config.admin_ids else '❌'}\n\n"
        )
    else:
        # Проверяем авторизацию для обычного пользователя
        is_authorized = await check_auth(user_id)

        if is_authorized:
            # Статус для авторизованного наставника
            status_text = (
                f"👤 {bold('Статус наставника')}\n\n"
                f"✅ Авторизация: Подтверждена\n"
                f"👥 Роль: Наставник\n\n"
                f"{bold('Активные функции:')}\n"
                f"• Новые ответы на задания: ✅ \n"
                f"• Оповещения о дедлайнах:  ✅ \n\n"
                f"Вы получаете все уведомления автоматически\\!"
            )
        else:
            # Статус для неавторизованного пользователя
            status_text = (
                f"👤 {bold('Информация о пользователе')}\n\n"
                f"🆔 ID: {user_id}\n"
                f"📝 Username: @{escape_markdown_v2(username)}\n"
                f"❌ Авторизация: Не пройдена\n\n"
                f"Для начала работы с ботом отправьте команду /start\\."
            )

    await message.answer(status_text)

# Обработчик для неизвестных команд
async def cmd_unknown(message: types.Message, config):
    user_id = message.from_user.id
    is_admin = user_id in config.admin_ids

    if is_admin:
        await message.answer(
            f"❌ Неизвестная команда\\.\n\n"
            f"Используйте /help для просмотра доступных административных команд\\."
        )
    else:
        await message.answer(
            f"❌ Неизвестная команда\\.\n\n"
            f"Используйте /help для просмотра доступных команд\\."
        )

def register_common_handlers(dp: Dispatcher, config):
    """
    Регистрирует общие обработчики.

    Args:
        dp: Диспетчер бота
        config: Конфигурация бота
    """
    dp.register_message_handler(
        lambda msg, state: cmd_start(msg, state, config),
        commands=["start"],
        state="*"
    )
    dp.register_message_handler(
        lambda msg: cmd_help(msg, config),
        commands=["help"],
        state="*"
    )
    dp.register_message_handler(
        lambda msg: cmd_about(msg, config),
        commands=["about"],
        state="*"
    )
    dp.register_message_handler(
        lambda msg: cmd_status(msg, config),
        commands=["status"],
        state="*"
    )
    dp.register_message_handler(
        lambda msg: cmd_unknown(msg, config),
        commands=["*"],
        state="*"
    )

    # Универсальный обработчик для всех текстовых сообщений (только если нет активного состояния)
    async def handle_text_no_state(message: types.Message):
        user_id = message.from_user.id
        is_admin = user_id in config.admin_ids

        if is_admin:
            await message.answer(
                f"Используйте команды для управления ботом\\.\n"
                f"Отправьте /help для просмотра доступных команд\\."
            )
        else:
            await message.answer(
                f"Для использования бота необходимо авторизоваться\\.\n"
                f"Пожалуйста, отправьте команду /start и следуйте инструкциям\\."
            )

    dp.register_message_handler(
        handle_text_no_state,
        state=None,
        content_types=types.ContentType.TEXT
    )
