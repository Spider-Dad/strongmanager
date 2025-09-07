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
from bot.utils.logger import setup_logger_with_alerts
from bot.utils.alerts import AlertHandler
from bot.services.sync_service import SyncService

# Задержка для предотвращения проблем с дублирующимися экземплярами бота на сервере
time.sleep(5)

# Загрузка переменных окружения
load_dotenv()

# Глобальные переменные для хранения обработчиков
alert_handler: Optional[AlertHandler] = None
db_log_handler = None
sync_service: Optional[SyncService] = None
logger = None

# Кэш для предотвращения повторной обработки дублирующихся обновлений
processed_updates = set()
MAX_PROCESSED_UPDATES = 1000  # Максимальное количество хранимых update_id

# Создание директорий для данных перенесено на конфигурацию (чтобы dev не зависел от CWD)

async def on_startup(dp):
    logger.info("Бот запущен")

async def main():
    global alert_handler, db_log_handler, sync_service, logger

    # Настройка логирования
    logger = logging.getLogger(__name__)

    try:
        # Инициализация конфигурации
        config = Config()

        # Создание директорий данных на основе конфигурации
        config.data_dir.mkdir(parents=True, exist_ok=True)
        (config.data_dir / "database").mkdir(parents=True, exist_ok=True)

        # Инициализация базы данных
        await setup_database(config)

        # Инициализация бота и диспетчера
        bot = Bot(token=config.bot_token, parse_mode="MarkdownV2")
        storage = MemoryStorage()
        dp = Dispatcher(bot, storage=storage)

        # Настройка логирования без отправки алертов в Telegram
        # Оставляем только запись логов в файлы и БД
        logger.info("Настройка логирования (без Telegram-алертов)")
        _, db_log_handler = setup_logger_with_alerts()

        # Настройка middlewares
        setup_middlewares(dp, config)

        # Регистрация всех обработчиков
        register_all_handlers(dp, config)

        # Инициализация сервиса синхронизации
        sync_service = SyncService(config)

        # Создание таблицы истории синхронизации если её нет
        await sync_service.ensure_sync_table()

        # Запуск автоматической синхронизации если настроена
        await sync_service.start_auto_sync()

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

        # Добавление задачи очистки старых логов
        cleanup_interval_hours = int(os.getenv("LOG_CLEANUP_INTERVAL_HOURS", "24"))
        from bot.utils.logger import cleanup_old_logs
        scheduler.add_job(
            cleanup_old_logs,
            'interval',
            hours=cleanup_interval_hours,
            id='cleanup_old_logs'
        )

        # Обработчик сигналов для корректного завершения
        async def on_shutdown(signal, frame):
            logger.info("Завершение работы бота...")

            # Остановка автоматической синхронизации
            if sync_service:
                await sync_service.stop_auto_sync()

            # Остановка обработчика алертов
            if alert_handler:
                alert_handler.stop()

            # Остановка обработчика логов БД
            if db_log_handler:
                db_log_handler.stop()

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

                        # Проверяем, не обрабатывали ли мы уже это обновление
                        update_id = update.update_id
                        if update_id in processed_updates:
                            logger.warning(f"Пропускаем дублирующееся обновление: {update_id}")
                            return web.Response()  # Возвращаем 200, чтобы Telegram не повторял запрос

                        # Добавляем update_id в кэш
                        processed_updates.add(update_id)

                        # Ограничиваем размер кэша
                        if len(processed_updates) > MAX_PROCESSED_UPDATES:
                            # Удаляем самые старые записи (простая стратегия)
                            oldest_updates = list(processed_updates)[:100]
                            for old_id in oldest_updates:
                                processed_updates.discard(old_id)

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
                        error_msg = str(e)
                        logger.error(f"Ошибка при обработке webhook: {error_msg}")

                        # Специальная обработка для ошибок таймаута callback query
                        if "Query is too old" in error_msg or "response timeout expired" in error_msg:
                            logger.warning("Обнаружена ошибка таймаута callback query - это нормально при долгих операциях")
                            # Возвращаем 200, чтобы Telegram не повторял запрос
                            return web.Response()

                        # Специальная обработка для ошибок парсинга MarkdownV2
                        if "Can't parse entities" in error_msg or "character '.' is reserved" in error_msg:
                            logger.warning(f"Обнаружена ошибка парсинга MarkdownV2: {error_msg}")
                            # Возвращаем 200, чтобы Telegram не повторял запрос
                            return web.Response()

                        # Специальная обработка для ошибок редактирования сообщений
                        if "Message can't be edited" in error_msg or "Message is not modified" in error_msg:
                            logger.warning(f"Обнаружена ошибка редактирования сообщения: {error_msg}")
                            # Возвращаем 200, чтобы Telegram не повторял запрос
                            return web.Response()

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
        # Остановка сервисов при завершении
        if sync_service:
            await sync_service.stop_auto_sync()
        if alert_handler:
            alert_handler.stop()
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise
    finally:
        # Закрываем все соединения при выходе
        try:
            # Остановка сервисов
            if sync_service:
                await sync_service.stop_auto_sync()
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
