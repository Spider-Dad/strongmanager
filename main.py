import asyncio
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

import aiogram
from aiogram import Bot, Dispatcher, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

from bot.config import Config
from bot.handlers import register_all_handlers
from bot.middlewares import setup_middlewares
from bot.services.database import setup_database
from bot.utils.logger import setup_logger, setup_logger_with_alerts
from bot.utils.alerts import AlertHandler

# Задержка для предотвращения проблем с дублирующимися экземплярами бота на сервере
time.sleep(5)

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования (базовая, без алертов пока)
setup_logger()
logger = logging.getLogger(__name__)

# Глобальная переменная для хранения обработчика алертов
alert_handler: Optional[AlertHandler] = None

# Создание директорий для данных
def create_data_directories():
    env = os.getenv("SERVER_ENV", "dev")
    if env == "prod":
        base_dir = Path("/data")
    else:
        base_dir = Path.cwd() / "data"

    # Создание директории для базы данных
    db_dir = base_dir / "database"
    db_dir.mkdir(parents=True, exist_ok=True)

    return base_dir, db_dir

async def on_startup(dp):
    logger.info("Бот запущен")

async def main():
    global alert_handler
    try:
        # Создание директорий
        base_dir, db_dir = create_data_directories()

        # Инициализация конфигурации
        config = Config()

        # Инициализация базы данных
        await setup_database(config)

        # Инициализация бота и диспетчера
        bot = Bot(token=config.bot_token, parse_mode="MarkdownV2")
        storage = MemoryStorage()
        dp = Dispatcher(bot, storage=storage)

        # Настройка системы алертов
        if config.admin_ids:
            logger.info(f"Настройка системы алертов для администраторов: {config.admin_ids}")
            alert_handler = setup_logger_with_alerts(bot, config.admin_ids)
        else:
            logger.warning("Список администраторов не настроен. Система алертов отключена.")

        # Настройка middlewares
        setup_middlewares(dp, config)

        # Регистрация всех обработчиков
        register_all_handlers(dp, config)

        # Инициализация планировщика для проверки уведомлений
        scheduler = AsyncIOScheduler()

        # Импорт здесь для избежания циклических импортов
        from bot.services.notifications import check_new_notifications

        # Добавление задачи проверки уведомлений
        scheduler.add_job(
            check_new_notifications,
            'interval',
            seconds=config.polling_interval,
            args=[bot, config]
        )

        # Обработчик сигналов для корректного завершения
        async def on_shutdown(signal, frame):
            logger.info("Завершение работы бота...")

            # Остановка обработчика алертов
            if alert_handler:
                alert_handler.stop()

            # Остановка планировщика
            scheduler.shutdown(wait=False)
            # Закрытие соединений с БД и других ресурсов
            await dp.storage.close()
            await dp.storage.wait_closed()
            await bot.session.close()
            sys.exit(0)

        # Регистрация обработчиков сигналов
        if os.name == 'posix':  # Для UNIX-подобных систем
            for sig in (signal.SIGINT, signal.SIGTERM):
                asyncio.get_event_loop().add_signal_handler(sig, lambda: asyncio.create_task(on_shutdown(sig, None)))
        else:
            logger.info("Запуск на Windows - обработка сигналов отключена.")

        # Запуск планировщика
        scheduler.start()

        # Запуск бота в режиме long polling или webhook в зависимости от конфигурации
        if config.env == "prod" and config.webhook_host:
            try:
                # Настройка webhook
                webhook_url = f"{config.webhook_host}{config.webhook_path}"
                await bot.set_webhook(webhook_url)
                logger.info(f"Запуск бота в режиме webhook на {webhook_url}")

                # Запуск web-сервера для обработки webhook-запросов
                from aiohttp import web

                app = web.Application()
                app['bot'] = bot  # Сохраняем bot
                app['dp'] = dp    # Сохраняем dp

                async def webhook_handler(request):
                    try:
                        update_dict = await request.json()
                        logger.debug(f"Получен webhook: {update_dict}")
                        update = aiogram.types.Update(**update_dict)
                        logger.debug(f"Создан объект Update: {update}")

                        # Получаем экземпляры Bot и Dispatcher из состояния приложения
                        current_bot = request.app['bot']
                        current_dp = request.app['dp']

                        # Устанавливаем текущие экземпляры для aiogram
                        aiogram.Bot.set_current(current_bot)
                        aiogram.Dispatcher.set_current(current_dp)

                        await current_dp.process_update(update)
                        logger.debug("Update успешно обработан")
                        return web.Response()
                    except Exception as e:
                        logger.error(f"Ошибка при обработке webhook: {e}")
                        # Важно не пытаться получить update_dict снова, если await request.json() уже вызвал ошибку
                        # или если update_dict не был определен.
                        update_data_for_log = locals().get('update_dict', 'Нет данных')
                        logger.error(f"Данные webhook: {update_data_for_log}")
                        return web.Response(status=500)

                app.router.add_post(config.webhook_path, webhook_handler)

                runner = web.AppRunner(app)
                await runner.setup()
                site = web.TCPSite(runner, '0.0.0.0', config.webhook_port)
                await site.start()

                logger.info("Webhook сервер запущен")

                # Держим приложение запущенным
                while True:
                    await asyncio.sleep(3600)  # Проверка каждый час
            except Exception as e:
                logger.error(f"Ошибка при запуске webhook: {e}")
                raise
        else:
            # Запуск в режиме long polling
            logger.info("Запуск бота в режиме long polling")
            # Пропускаем накопившиеся обновления
            await bot.delete_webhook(drop_pending_updates=True)
            # Запускаем поллинг
            await dp.start_polling()

    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
        # Остановка обработчика алертов при завершении
        if alert_handler:
            alert_handler.stop()
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise
    finally:
        # Закрываем все соединения при выходе
        try:
            # Остановка обработчика алертов
            if alert_handler:
                alert_handler.stop()

            await dp.storage.close()
            await dp.storage.wait_closed()
            await bot.session.close()
        except Exception as e:
            logger.error(f"Ошибка при закрытии соединений: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise
