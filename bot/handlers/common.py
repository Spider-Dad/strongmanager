import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from bot.handlers.auth import Registration, check_auth
from bot.utils.markdown import bold, italic, escape_markdown_v2
from bot.keyboards.main_menu import kb_main_menu_admin, kb_main_menu_mentor, kb_back_to_main
from bot.services.database import get_session

logger = logging.getLogger(__name__)

# Текстовые билдеры для главного меню и справки (MarkdownV2)
def build_start_admin_text() -> str:
	return "\n".join([
		f"👋 {bold('Добро пожаловать в бот-помощник наставника онлайн школы Strong Manager!')}",
		"",
		escape_markdown_v2("Вы имеете доступ к административным функциям бота."),
		"",
		escape_markdown_v2("• Как Администратор вы можете отслеживать статус успеваемости студентов по наставникам."),
		escape_markdown_v2("• Если за вами закреплены студенты в роли Наставника, вы также будете получать все соответствующие уведомления. Бот работает автоматически и не требует от вас никаких действий. Просто держите уведомления включенными!"),
		"",
		escape_markdown_v2("Выберите действие:"),
	])


def build_start_mentor_text() -> str:
	return "\n".join([
		f"👋 {bold('Добро пожаловать в бот-помощник наставника онлайн школы Strong Manager!')}",
		"",
		escape_markdown_v2("Здесь вы будете получать уведомления о действиях ваших студентов."),
		escape_markdown_v2("Бот работает автоматически и не требует от вас никаких действий."),
		escape_markdown_v2("Просто держите уведомления включенными!"),
		"",
		escape_markdown_v2("Выберите действие:"),
	])


def build_about_admin_text() -> str:
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
		escape_markdown_v2("• Напоминания об ответах ваших студентов на задания"),
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
		escape_markdown_v2("⌛ -  Ответ на активный урок студентом не предоставлен (на момент генерации отчета)"),
		escape_markdown_v2("❌ -  Ответа на завершенный урок не предоставлен."),
	]
	return "\n".join(lines)


def build_about_mentor_text() -> str:
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
		escape_markdown_v2("• Напоминания об ответах ваших студентов на задания"),
		escape_markdown_v2("• Приближающиеся дедлайны по ответам на задания"),
		"",
		bold("Аналитика:"),
		"",
		escape_markdown_v2("/progress - Табель успеваемости ваших студентов"),
		escape_markdown_v2("  • Оперативная статистика по предоставленным ответам студентов на задание уроков"),
		escape_markdown_v2("  • Статистика по активным и завершенным тренингам, урокам"),
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
		escape_markdown_v2("⌛ -  Ответ на активный урок студентом не предоставлен (на момент генерации отчета)"),
		escape_markdown_v2("❌ -  Ответа на завершенный урок не предоставлен"),
	]
	return "\n".join(lines)

# Обработчик команды /start
async def cmd_start(message: types.Message, state: FSMContext, config):
    # Сначала сбрасываем любые существующие состояния
    await state.finish()

    user_id = message.from_user.id
    is_admin = user_id in config.admin_ids

    def build_start_admin_text() -> str:
        return "\n".join([
            f"👋 {bold('Добро пожаловать в бот-помощник наставника онлайн школы Strong Manager!')}",
            "",
            escape_markdown_v2("Вы имеете доступ к административным функциям бота."),
            "",
            escape_markdown_v2("• Как Администратор вы можете отслеживать статус успеваемости студентов по наставникам."),
            escape_markdown_v2("• Если за вами закреплены студенты в роли Наставника, вы также будете получать все соответствующие уведомления. Бот работает автоматически и не требует от вас никаких действий. Просто держите уведомления включенными!"),
            "",
            escape_markdown_v2("Выберите действие:"),
        ])

    def build_start_mentor_text() -> str:
        return "\n".join([
            f"👋 {bold('Добро пожаловать в бот-помощник наставника онлайн школы Strong Manager!')}",
            "",
            escape_markdown_v2("Здесь вы будете получать уведомления о действиях ваших студентов."),
            escape_markdown_v2("Бот работает автоматически и не требует от вас никаких действий."),
            escape_markdown_v2("Просто держите уведомления включенными!"),
            "",
            escape_markdown_v2("Выберите действие:"),
        ])

    # Для администраторов показываем специальное приветствие
    if is_admin:
        await message.answer(build_start_admin_text(), parse_mode='MarkdownV2', reply_markup=kb_main_menu_admin())
    else:
        # Проверяем, авторизован ли обычный пользователь
        is_authorized = await check_auth(user_id)

        if is_authorized:
            # Для авторизованных наставников
            await message.answer(build_start_mentor_text(), parse_mode='MarkdownV2', reply_markup=kb_main_menu_mentor())
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

    def build_about_admin_text() -> str:
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
            escape_markdown_v2("• Напоминания об ответах ваших студентов на задания"),
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
            escape_markdown_v2("⌛ -  Ответ на активный урок студентом не предоставлен (на момент генерации отчета)"),
            escape_markdown_v2("❌ -  Ответа на завершенный урок не предоставлен."),
        ]
        return "\n".join(lines)

    def build_about_mentor_text() -> str:
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
            escape_markdown_v2("• Напоминания об ответах ваших студентов на задания"),
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
            escape_markdown_v2("⌛ -  Ответ на активный урок студентом не предоставлен (на момент генерации отчета)"),
            escape_markdown_v2("❌ -  Ответа на завершенный урок не предоставлен."),
        ]
        return "\n".join(lines)

    if is_admin:
        await message.answer(build_about_admin_text(), parse_mode='MarkdownV2', reply_markup=kb_back_to_main())
    else:
        await message.answer(build_about_mentor_text(), parse_mode='MarkdownV2', reply_markup=kb_back_to_main())

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
            f"⚠️ {bold('Доступ ограничен')}\n\n"
            f"Выбранная команда доступна только администраторам\\.\n\n"
            f"Если вы наставник, используйте доступные вам команды:\n"
            f"/start \\- Главное меню\n"
            f"/about \\- Информация о боте\n"
            f"/progress \\- Табель успеваемости ваших студентов"
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

    # Роутер кликов главного меню (inline)
    from aiogram.types import CallbackQuery

    async def main_menu_router(callback: CallbackQuery):
        data = callback.data or ""
        user_id = callback.from_user.id
        is_admin = user_id in config.admin_ids
        # Стартовое меню
        if data == "mm:start":
            # Ререндерим старт по роли в текущем сообщении
            if is_admin:
                text = build_start_admin_text()
                kb = kb_main_menu_admin()
            else:
                text = build_start_mentor_text()
                kb = kb_main_menu_mentor()
            await callback.message.edit_text(text, parse_mode='MarkdownV2')
            await callback.message.edit_reply_markup(reply_markup=kb)
            await callback.answer()
            return
        if data == "mm:about":
            text = build_about_admin_text() if is_admin else build_about_mentor_text()
            await callback.message.edit_text(text, parse_mode='MarkdownV2')
            await callback.message.edit_reply_markup(reply_markup=kb_back_to_main())
            await callback.answer()
            return
        if data == "mm:progress":
            # Немедленно отвечаем на callback query
            await callback.answer("Загрузка...")

            try:
                if is_admin:
                    # Для админа открываем список админа
                    from bot.handlers.gradebook import _render_admin_list
                    async for session in get_session():
                        await _render_admin_list(callback.message, session, training_id=None, lesson_id=None, page=1, edit=True)
                else:
                    from sqlalchemy import select
                    from bot.services.database import Mentor
                    async for session in get_session():
                        res = await session.execute(select(Mentor).where(Mentor.telegram_id == user_id))
                        mentor = res.scalars().first()
                        if mentor:
                            from bot.handlers.gradebook import _render_students_list
                            await _render_students_list(callback.message, session, mentor_id=mentor.id, training_id=None, lesson_id=None, page=1, edit=True)
                        else:
                            await callback.answer("Нет доступа", show_alert=True)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Ошибка при рендеринге прогресса: {e}")
                await callback.message.edit_text("❌ Произошла ошибка при загрузке данных — попробуйте еще раз")
            return
        if data == "mm:sync":
            if user_id in config.admin_ids:
                from bot.handlers.admin import callback_sync_menu
                await callback_sync_menu(callback)
                await callback.answer()
            else:
                await callback.answer("Доступно только администраторам", show_alert=True)
            return
        if data == "mm:alerts":
            if user_id in config.admin_ids:
                from bot.handlers.admin import callback_alerts_menu
                await callback_alerts_menu(callback)
                await callback.answer()
            else:
                await callback.answer("Доступно только администраторам", show_alert=True)
            return

    dp.register_callback_query_handler(
        main_menu_router,
        lambda c: c.data and c.data.startswith("mm:"),
        state="*"
    )
