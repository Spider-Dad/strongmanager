import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from bot.handlers.auth import Registration, check_auth

logger = logging.getLogger(__name__)

# Обработчик команды /start
async def cmd_start(message: types.Message, state: FSMContext, config):
    # Сначала сбрасываем любые существующие состояния
    await state.finish()

    # Проверяем, авторизован ли пользователь
    is_authorized = await check_auth(message.from_user.id)

    if is_authorized:
        # Для авторизованных пользователей
        await message.answer(
            "👋 Добро пожаловать в бот-помощник наставника онлайн школы Strong Manager!\n\n"
            "Здесь вы будете получать уведомления о действиях ваших студентов.\n\n"
            "Доступные команды:\n"
            "/help - Показать справку\n"
            "/about - Информация о боте"
        )
    else:
        # Для неавторизованных пользователей
        await message.answer(
            "Здравствуйте! Для регистрации введите ваш email, который используется в онлайн школе для руководителей Strong Manager"
        )
        # Устанавливаем состояние ожидания email
        await Registration.waiting_for_email.set()

# Обработчик команды /help
async def cmd_help(message: types.Message, config):
    # Проверяем, авторизован ли пользователь
    is_authorized = await check_auth(message.from_user.id)

    if is_authorized:
        await message.answer(
            "📚 <b>Справка по использованию бота</b>\n\n"
            "<b>Основные команды:</b>\n"
            "/start - Перезапустить бота\n"
            "/help - Показать эту справку\n"
            "/about - Информация о боте\n\n"
            "Бот автоматически отправляет уведомления о действиях ваших студентов."
        )
    else:
        await message.answer(
            "Для начала работы с ботом необходимо авторизоваться.\n"
            "Пожалуйста, отправьте команду /start и следуйте инструкциям."
        )

# Обработчик команды /about
async def cmd_about(message: types.Message, config):
    await message.answer(
        "📱 <b>Бот-помощник наставника онлайн школы Strong Manager</b>\n\n"
        "Версия: 1.0.0\n\n"
        "Этот бот предназначен для оперативного оповещения наставников о действиях студентов:\n"
        "• Новые ответы на задания\n"
        "• Комментарии к заданиям\n\n"
        "При возникновении вопросов обращайтесь к администратору."
    )

# Обработчик для неизвестных команд
async def cmd_unknown(message: types.Message):
    await message.answer(
        "Неизвестная команда. Используйте /help для просмотра доступных команд."
    )

def register_common_handlers(dp: Dispatcher, config):
    """
    Регистрирует общие обработчики.

    Args:
        dp: Диспетчер бота
        config: Конфигурация бота
    """
    dp.register_message_handler(
        cmd_start,
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
        cmd_unknown,
        commands=["*"],
        state="*"
    )

    # Универсальный обработчик для всех текстовых сообщений (только если нет активного состояния)
    dp.register_message_handler(
        lambda message: message.answer(
            "Для использования бота необходимо авторизоваться.\nПожалуйста, отправьте команду /start и следуйте инструкциям."
        ),
        state=None,
        content_types=types.ContentType.TEXT
    )
