import logging
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware

from bot.handlers.auth import check_auth

logger = logging.getLogger(__name__)

class AuthMiddleware(BaseMiddleware):
    """
    Middleware для проверки авторизации пользователей.
    Добавляет в данные хендлера флаг is_authorized.
    """

    async def on_pre_process_message(self, message: types.Message, data: dict):
        # Проверяем, находится ли пользователь в состоянии регистрации
        # Если да, то пропускаем проверку авторизации
        state = data.get('state')
        if state and await state.get_state() == 'Registration:waiting_for_email':
            return

        # Пропускаем служебные сообщения
        if message.is_command() and message.get_command() in ['/start', '/help', '/about']:
            return

        # Проверяем авторизацию
        is_authorized = await check_auth(message.from_user.id)
        data['is_authorized'] = is_authorized
        # Не отправляем никаких сообщений и не останавливаем обработку
