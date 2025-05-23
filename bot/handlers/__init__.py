from bot.handlers.auth import register_auth_handlers
from bot.handlers.common import register_common_handlers
from bot.handlers.admin import register_admin_handlers
from bot.handlers.notifications import register_notification_handlers

def register_all_handlers(dp, config):
    """
    Регистрирует все обработчики сообщений.

    Args:
        dp: Диспетчер бота
        config: Конфигурация бота
    """
    # Порядок регистрации важен - обработчики регистрируются в порядке добавления
    register_auth_handlers(dp, config)
    register_common_handlers(dp, config)
    register_admin_handlers(dp, config)
    register_notification_handlers(dp, config)
