from bot.handlers.auth import register_auth_handlers
from bot.handlers.common import register_common_handlers
from bot.handlers.admin import register_admin_handlers
from bot.handlers.notifications import register_notification_handlers
from bot.handlers.gradebook import register_gradebook_handlers

def register_all_handlers(dp, config):
    """
    Регистрирует все обработчики сообщений.

    Args:
        dp: Диспетчер бота
        config: Конфигурация бота
    """
    # Порядок регистрации важен - обработчики регистрируются в порядке добавления
    # Сначала регистрируем команды администратора (они должны быть первыми)
    register_admin_handlers(dp, config)
    # Затем регистрируем общие команды (включая перехват админских команд для неадминов)
    register_common_handlers(dp, config)
    # Затем обработчики авторизации
    register_auth_handlers(dp, config)
    # Регистрируем хендлеры табеля (не конфликтуют с админскими)
    register_gradebook_handlers(dp, config)
    # И в конце - обработчики уведомлений
    register_notification_handlers(dp, config)
