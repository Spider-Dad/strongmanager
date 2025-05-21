from bot.middlewares.auth import AuthMiddleware

def setup_middlewares(dp, config):
    """
    Настраивает middleware для диспетчера.

    Args:
        dp: Диспетчер бота
        config: Конфигурация бота
    """
    # Регистрация middleware для проверки авторизации
    dp.middleware.setup(AuthMiddleware())
