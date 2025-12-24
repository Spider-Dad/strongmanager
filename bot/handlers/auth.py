import logging
import re
from datetime import datetime

import pytz
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from sqlalchemy import select

from bot.services.database import Mentor, get_session
from bot.utils.markdown import bold

logger = logging.getLogger(__name__)

# Состояния для регистрации
class Registration(StatesGroup):
    waiting_for_email = State()

# Проверка валидности email
def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return re.match(pattern, email) is not None

# Обработчик ввода email
async def process_email(message: types.Message, state: FSMContext, config):
    email = message.text.strip().lower()

    # Проверка валидности email
    if not is_valid_email(email):
        await message.answer(f"Некорректный формат email\\. Пожалуйста, введите правильный email\\.")
        return  # Сохраняем текущее состояние

    try:
        # Прямая работа с PostgreSQL
        async for session in get_session():
            # Текущая дата в UTC для проверки актуальности записи
            now_utc = datetime.now(pytz.UTC)

            # Поиск активного ментора по email в PostgreSQL
            # Проверяем, что email существует и запись актуальна:
            # - текущая дата >= valid_from
            # - текущая дата <= valid_to
            mentor_query = select(Mentor).where(
                Mentor.email == email,
                Mentor.valid_from <= now_utc,
                Mentor.valid_to >= now_utc
            )
            result = await session.execute(mentor_query)
            mentor = result.scalars().first()

            if not mentor:
                await message.answer(
                    f"Email не найден в базе менторов онлайн школы Strong Manager\\. "
                    f"Пожалуйста, проверьте правильность ввода или обратитесь к администратору\\."
                )
                return

            # Обновление telegram_id
            mentor.telegram_id = message.from_user.id
            mentor.username = message.from_user.username
            # Примечание: first_name и last_name НЕ обновляются при регистрации

            await session.commit()

            await state.finish()
            await message.answer(
                f"{bold('Вы успешно зарегистрированы в системе оповещений как наставник!')}\n\n"
                f"Теперь вы будете получать уведомления о действиях ваших студентов\\.\n\n"
                f"Откройте /start для главного меню или /about для справки\\."
            )

            logger.info(f"Ментор {message.from_user.id} ({email}) зарегистрирован")

    except Exception as e:
        logger.error(f"Ошибка при регистрации: {e}", exc_info=True)
        await message.answer(
            f"Произошла ошибка при регистрации\\. "
            f"Пожалуйста, попробуйте позже или обратитесь к администратору\\."
        )
        await state.finish()

# Проверка авторизации пользователя
async def check_auth(telegram_id):
    """Проверка авторизации через PostgreSQL"""
    try:
        async for session in get_session():
            # Текущая дата в UTC для проверки актуальности записи
            now_utc = datetime.now(pytz.UTC)

            # Проверяем, что ментор существует и запись актуальна:
            # - текущая дата >= valid_from
            # - текущая дата <= valid_to
            mentor_query = select(Mentor).where(
                Mentor.telegram_id == telegram_id,
                Mentor.valid_from <= now_utc,
                Mentor.valid_to >= now_utc
            )
            result = await session.execute(mentor_query)
            mentor = result.scalars().first()
            return mentor is not None
    except Exception as e:
        logger.error(f"Ошибка при проверке авторизации пользователя {telegram_id}: {e}")
        return False

def register_auth_handlers(dp: Dispatcher, config):
    """
    Регистрирует обработчики авторизации.

    Args:
        dp: Диспетчер бота
        config: Конфигурация бота
    """
    dp.register_message_handler(
        lambda msg, state: process_email(msg, state, config),
        state=Registration.waiting_for_email
    )
