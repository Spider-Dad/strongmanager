import logging
import re
from datetime import datetime

from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from sqlalchemy import select

from bot.services.api import get_mentor_by_email, register_telegram_id, ApiError
from bot.services.database import Mentor, get_session

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
        await message.answer("Некорректный формат email. Пожалуйста, введите правильный email.")
        return  # Сохраняем текущее состояние

    try:
        # Регистрация Telegram ID в Google Sheets напрямую
        # Если ментор с таким email не существует, API вернет ошибку
        registration_result = await register_telegram_id(
            config.api_url,
            email,
            message.from_user.id,
            message.from_user.username
        )

        # Если мы дошли сюда, значит регистрация в API успешна
        # Сохраняем информацию о менторе в локальной БД
        async for session in get_session():
            # Проверка, существует ли уже такой ментор по email
            existing_mentor = await session.execute(
                select(Mentor).where(Mentor.email == email)
            )
            existing_mentor = existing_mentor.scalars().first()

            if existing_mentor:
                # Обновление существующего ментора
                existing_mentor.telegram_id = message.from_user.id
                existing_mentor.first_name = message.from_user.first_name
                existing_mentor.last_name = message.from_user.last_name
                existing_mentor.username = message.from_user.username
                # Если есть поле updated_at, можно обновить его здесь
            else:
                # Создание нового ментора
                new_mentor = Mentor(
                    telegram_id=message.from_user.id,
                    email=email,
                    first_name=message.from_user.first_name,
                    last_name=message.from_user.last_name,
                    username=message.from_user.username
                )
                session.add(new_mentor)

            await session.commit()

        # Завершение состояния регистрации
        await state.finish()

        # Отправка приветственного сообщения
        await message.answer(
            f"Вы успешно зарегистрированы в системе оповещений как ментор!\n\n"
            f"Теперь вы будете получать уведомления о действиях ваших студентов.\n\n"
            f"Для просмотра доступных команд используйте /help."
        )

        logger.info(f"Ментор {message.from_user.id} ({email}) успешно зарегистрирован")

    except ApiError as e:
        error_message = str(e)
        if "Mentor with this email not found" in error_message:
            await message.answer("Email не найден в базе менторов онлайн школы Strong Manager. Пожалуйста, проверьте правильность ввода или обратитесь к администратору.")
        else:
            logger.error(f"Ошибка API при регистрации ментора {message.from_user.id} ({email}): {e}")
            await message.answer("Произошла ошибка при регистрации. Пожалуйста, попробуйте позже или обратитесь к администратору.")
            await state.finish()  # Сбрасываем состояние при критической ошибке

    except Exception as e:
        logger.error(f"Ошибка при регистрации ментора {message.from_user.id} ({email}): {e}")
        await message.answer("Произошла ошибка при регистрации. Пожалуйста, попробуйте позже или обратитесь к администратору.")
        await state.finish()  # Сбрасываем состояние при критической ошибке

# Проверка авторизации пользователя
async def check_auth(telegram_id):
    try:
        async for session in get_session():
            mentor = await session.execute(
                select(Mentor).where(
                    Mentor.telegram_id == telegram_id
                )
            )
            mentor = mentor.scalars().first()
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
