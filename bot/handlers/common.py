import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from bot.handlers.auth import Registration, check_auth
from bot.utils.markdown import bold, italic, escape_markdown_v2

logger = logging.getLogger(__name__)

# Обработчик команды /start
async def cmd_start(message: types.Message, state: FSMContext, config):
    # Сначала сбрасываем любые существующие состояния
    await state.finish()

    user_id = message.from_user.id
    is_admin = user_id in config.admin_ids

    # Для администраторов показываем специальное приветствие
    if is_admin:
        lines = [
            f"👋 {bold('Добро пожаловать в бот-помощник наставника онлайн школы Strong Manager!')}",
            "",
            escape_markdown_v2("Вы имеете доступ к административным функциям бота."),
            "",
            escape_markdown_v2("• Как Администратор вы можете отслеживать статус успеваемости студентов по наставникам."),
            escape_markdown_v2("• Если за вами закреплены студенты в роли Наставника, вы также будете получать все соответствующие уведомления. Бот работает автоматически и не требует от вас никаких действий. Просто держите уведомления включенными!"),
            "",
            escape_markdown_v2("Выберите действие:"),
        ]

        # Клавиатура: row_width=1
        kb = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
        kb.add(
            types.KeyboardButton("/start"),
        )
        kb.add(
            types.KeyboardButton("/about"),
        )
        kb.add(
            types.KeyboardButton("/progress_admin"),
        )
        kb.add(
            types.KeyboardButton("/sync"),
        )
        kb.add(
            types.KeyboardButton("/alerts"),
        )

        await message.answer("\n".join(lines), parse_mode='MarkdownV2', reply_markup=kb)
    else:
        # Проверяем, авторизован ли обычный пользователь
        is_authorized = await check_auth(user_id)

        if is_authorized:
            # Для авторизованных наставников
            lines = [
                f"👋 {bold('Добро пожаловать в бот-помощник наставника онлайн школы Strong Manager!')}",
                "",
                escape_markdown_v2("Здесь вы будете получать уведомления о действиях ваших студентов."),
                escape_markdown_v2("Бот работает автоматически и не требует от вас никаких действий."),
                escape_markdown_v2("Просто держите уведомления включенными!"),
                "",
                escape_markdown_v2("Выберите действие:"),
            ]

            kb = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
            kb.add(types.KeyboardButton("/start"))
            kb.add(types.KeyboardButton("/about"))
            kb.add(types.KeyboardButton("/progress"))

            await message.answer("\n".join(lines), parse_mode='MarkdownV2', reply_markup=kb)
        else:
            # Для неавторизованных пользователей
            await message.answer(
                "Здравствуйте\\! Для регистрации введите ваш email, который используется в онлайн школе для руководителей Strong Manager"
            )
            # Устанавливаем состояние ожидания email
            await Registration.waiting_for_email.set()

# Команда /help удалена

# Обработчик команды /about
async def cmd_about(message: types.Message, config):
    user_id = message.from_user.id
    is_admin = user_id in config.admin_ids

    if is_admin:
        # Справка по функциональным возможностям (Администратор)
        lines = [
            f"📱 {bold('Справка по функциональным возможностям бота')}",
            "",
            escape_markdown_v2("Роли в боте:"),
            "",
            escape_markdown_v2("• Вы вошли как Администратор — имеете доступ ко всем функциям управления."),
            escape_markdown_v2("• Если за вами закреплены студенты, вы также выступаете в роли Наставника и будете получать все его уведомления."),
            "",
            escape_markdown_v2("Основные функции:"),
            "",
            bold("Оповещения:") + escape_markdown_v2(" (для вашей роли Наставника)"),
            "",
            escape_markdown_v2("• Новые ответы на задания ваших студентов"),
            escape_markdown_v2("• Приближающиеся дедлайны по ответам на задания"),
            "",
            bold("Администрирование:"),
            "",
            escape_markdown_v2("/sync - Синхронизация БД с Google Sheets:"),
            escape_markdown_v2("• Ручная синхронизация данных"),
            escape_markdown_v2("• Просмотр статуса синхронизации"),
            escape_markdown_v2("• Текущие настройки автосинхронизации"),
            "",
            escape_markdown_v2("/alerts - Статус по ошибкам бота:"),
            escape_markdown_v2("• Последние ошибки бота с типом CRITICAL, ERROR"),
            escape_markdown_v2("• Количество ошибок бота по модулям за последние сутки с типом CRITICAL, ERROR, WARNING"),
            "",
            bold("Аналитика:"),
            "",
            escape_markdown_v2("/progress_admin - Табель успеваемости студентов по всем наставникам:"),
            escape_markdown_v2("  • Оперативная статистика по предоставленным ответам студентов на задание уроков"),
            escape_markdown_v2("  • Статистика по активным и завершенным тренингам, урокам."),
            escape_markdown_v2("  • Возможность выбрать определенный тренинг и урок"),
            "",
            escape_markdown_v2("Условные обозначения в системе табеля:"),
            "",
            escape_markdown_v2("🟢 -  На момент отчета тренинг или урок завершен"),
            escape_markdown_v2("🟡 -  На момент отчета тренинг или урок активный"),
            escape_markdown_v2("🔴 -  На момент отчета тренинг или урок не начат"),
            "",
            escape_markdown_v2("✅ -  Ответ на завершенный урок студентом предоставлен вовремя (до завершения урока)"),
            escape_markdown_v2("⏰ -  Ответ на завершенный урок студентом предоставлен с опозданием (после завершения урока)"),
            escape_markdown_v2("⌛ -  Ответ на активный урок студентом предоставлен вовремя (на момент отчета урок активный)"),
            escape_markdown_v2("❌ -  Ответа на завершенный урок не предоставлен."),
        ]
        await message.answer("\n".join(lines), parse_mode='MarkdownV2')
    else:
        # Справка по функциональным возможностям (Наставник)
        lines = [
            f"📱 {bold('Справка по функциональным возможностям бота')}",
            "",
            escape_markdown_v2("Этот бот предназначен для оперативного оповещения наставников о действиях студентов."),
            "",
            bold("Основные функции:"),
            "",
            bold("Оповещения:"),
            "",
            escape_markdown_v2("• Новые ответы на задания ваших студентов"),
            escape_markdown_v2("• Приближающиеся дедлайны по ответам на задания"),
            "",
            bold("Аналитика:"),
            "",
            escape_markdown_v2("/progress - Табель успеваемости ваших студентов"),
            escape_markdown_v2("  • Оперативная статистика по предоставленным ответам студентов на задание уроков"),
            escape_markdown_v2("  • Статистика по активным и завершенным тренингам, урокам."),
            escape_markdown_v2("  • Возможность выбрать определенный тренинг и урок"),
            "",
            escape_markdown_v2("Условные обозначения в системе табеля:"),
            "",
            escape_markdown_v2("🟢 -  На момент отчета тренинг или урок завершен"),
            escape_markdown_v2("🟡 -  На момент отчета тренинг или урок активный"),
            escape_markdown_v2("🔴 -  На момент отчета тренинг или урок не начат"),
            "",
            escape_markdown_v2("✅ -  Ответ на завершенный урок студентом предоставлен вовремя (до завершения урока)"),
            escape_markdown_v2("⏰ -  Ответ на завершенный урок студентом предоставлен с опозданием (после завершения урока)"),
            escape_markdown_v2("⌛ -  Ответ на активный урок студентом предоставлен вовремя (на момент отчета урок активный)"),
            escape_markdown_v2("❌ -  Ответа на завершенный урок не предоставлен."),
        ]
        await message.answer("\n".join(lines), parse_mode='MarkdownV2')

# Команда /status удалена

# Обработчик для неизвестных команд
async def cmd_unknown(message: types.Message, config):
    user_id = message.from_user.id
    is_admin = user_id in config.admin_ids

    if is_admin:
        await message.answer(
            f"❌ {escape_markdown_v2('Неизвестная команда.')}\n\n"
            f"{escape_markdown_v2('Откройте /about для справки по функциям или /start для главного меню.')}",
            parse_mode='MarkdownV2'
        )
    else:
        await message.answer(
            f"❌ {escape_markdown_v2('Неизвестная команда.')}\n\n"
            f"{escape_markdown_v2('Откройте /about для справки по функциям или /start для главного меню.')}",
            parse_mode='MarkdownV2'
        )

# Обработчик для административных команд от неадминистраторов
async def handle_admin_commands_for_non_admins(message: types.Message, config):
    """Обработчик для административных команд, вызванных не администраторами"""
    user_id = message.from_user.id
    is_admin = user_id in config.admin_ids

    if not is_admin:
        await message.answer(
            f"⚠️ {bold('Доступ запрещён')}\n\n"
            f"Команды /alerts, /sync и другие административные команды доступны только администраторам\\.\n\n"
            f"Если вы наставник, используйте доступные вам команды:\n"
            f"/start \\- Главное меню\n"
            f"/help \\- Показать справку\n"
            f"/about \\- Информация о боте\n"
            f"/status \\- Проверить свой статус"
        )

def register_common_handlers(dp: Dispatcher, config):
    """
    Регистрирует общие обработчики.

    Args:
        dp: Диспетчер бота
        config: Конфигурация бота
    """
    # Регистрируем обработчик для административных команд от неадминистраторов
    # Этот обработчик должен быть зарегистрирован ДО регистрации административных обработчиков
    dp.register_message_handler(
        lambda msg: handle_admin_commands_for_non_admins(msg, config),
        lambda msg: msg.from_user.id not in config.admin_ids,
        commands=["alerts", "sync"],
        state="*"
    )

    dp.register_message_handler(
        lambda msg, state: cmd_start(msg, state, config),
        commands=["start"],
        state="*"
    )
    # Команда /help удалена
    dp.register_message_handler(
        lambda msg: cmd_about(msg, config),
        commands=["about"],
        state="*"
    )
    # Команда /status удалена
    dp.register_message_handler(
        lambda msg: cmd_unknown(msg, config),
        commands=["*"],
        state="*"
    )

    # Универсальный обработчик для всех текстовых сообщений (только если нет активного состояния)
    async def handle_text_no_state(message: types.Message):
        user_id = message.from_user.id
        is_admin = user_id in config.admin_ids
        is_authorized = await check_auth(user_id)

        if is_admin:
            await message.answer(
                escape_markdown_v2("Используйте /start для главного меню или /about для справки."),
                parse_mode='MarkdownV2'
            )
        elif is_authorized:
            # Для авторизованных наставников показываем то же сообщение
            await message.answer(
                escape_markdown_v2("Используйте /start для главного меню или /about для справки."),
                parse_mode='MarkdownV2'
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
