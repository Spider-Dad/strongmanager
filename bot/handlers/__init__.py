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
    # 1) Сначала админские — чтобы их не перехватил универсальный хендлер
    register_admin_handlers(dp, config)
    # 2) Затем — хендлеры табеля (новые команды), чтобы их не перехватывал unknown из common
    if getattr(config, 'gradebook_enabled', False):
        register_gradebook_handlers(dp, config)
    # 3) Общие команды и unknown — должны регистрироваться ПОСЛЕ специфичных
    register_common_handlers(dp, config)
    # 4) Авторизация — без влияния на порядок команд
    register_auth_handlers(dp, config)
    # 5) Уведомления — в конце
    register_notification_handlers(dp, config)
