import logging
from aiogram import Dispatcher

logger = logging.getLogger(__name__)

# В будущем здесь будут обработчики для управления уведомлениями
# Например, включение/отключение определенных типов уведомлений

def register_notification_handlers(dp: Dispatcher, config):
    """
    Регистрирует обработчики для управления уведомлениями.

    Args:
        dp: Диспетчер бота
        config: Конфигурация бота
    """
    # На данный момент обработчиков нет, но сохраняем функцию для будущего расширения
    pass
