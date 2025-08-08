import logging
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List
import asyncio
from aiogram import Bot
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

import bot.services.database as db

class DatabaseHandler(logging.Handler):
    """Обработчик для записи логов в базу данных"""

    def __init__(self, level=logging.NOTSET):
        super().__init__(level)
        self._queue = asyncio.Queue()
        self._task = None

    def emit(self, record):
        """Добавляет запись в очередь для асинхронной записи в БД"""
        try:
            # Получаем информацию о месте вызова
            if record.exc_info:
                traceback = self.formatException(record.exc_info)
            else:
                traceback = None

            log_data = {
                'timestamp': datetime.fromtimestamp(record.created),
                'level': record.levelname,
                'logger_name': record.name,
                'message': record.getMessage(),
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno,
                'traceback': traceback
            }

            # Добавляем в очередь (неблокирующе)
            try:
                self._queue.put_nowait(log_data)
            except asyncio.QueueFull:
                # Если очередь переполнена, просто игнорируем
                pass

        except Exception:
            # Не логируем ошибки логирования
            pass

    async def _write_to_db(self):
        """Асинхронная запись логов в БД"""
        while True:
            try:
                # Проверяем, что async_session инициализирован
                if db.async_session is None:
                    await asyncio.sleep(5)
                    continue

                # Получаем все записи из очереди
                logs_to_write = []
                errors_to_write = []

                # Собираем записи (максимум 100 за раз)
                for _ in range(100):
                    try:
                        log_data = self._queue.get_nowait()
                        logs_to_write.append(log_data)

                        # Если это ошибка, добавляем и в таблицу ошибок
                        if log_data['level'] in ['WARNING', 'ERROR', 'CRITICAL']:
                            errors_to_write.append(log_data)

                    except asyncio.QueueEmpty:
                        break

                if logs_to_write:
                    try:
                        async with db.async_session() as session:
                            # Записываем все логи
                            for log_data in logs_to_write:
                                app_log = db.ApplicationLog(
                                    timestamp=log_data['timestamp'],
                                    level=log_data['level'],
                                    logger_name=log_data['logger_name'],
                                    message=log_data['message'],
                                    module=log_data['module'],
                                    function=log_data['function'],
                                    line=log_data['line']
                                )
                                session.add(app_log)

                            # Записываем ошибки отдельно
                            for log_data in errors_to_write:
                                error_log = db.ErrorLog(
                                    timestamp=log_data['timestamp'],
                                    level=log_data['level'],
                                    logger_name=log_data['logger_name'],
                                    message=log_data['message'],
                                    traceback=log_data['traceback'],
                                    module=log_data['module'],
                                    function=log_data['function'],
                                    line=log_data['line']
                                )
                                session.add(error_log)

                            await session.commit()
                    except Exception as db_error:
                        print(f"Ошибка записи в БД: {db_error}", file=sys.stderr)

                # Пауза перед следующей проверкой
                await asyncio.sleep(5)

            except Exception as e:
                # Логируем ошибки записи в БД в stderr
                print(f"Ошибка записи логов в БД: {e}", file=sys.stderr)
                await asyncio.sleep(10)

    def start(self):
        """Запускает асинхронную задачу записи в БД"""
        if self._task is None:
            self._task = asyncio.create_task(self._write_to_db())

    def stop(self):
        """Останавливает асинхронную задачу"""
        if self._task:
            self._task.cancel()
            self._task = None

class DailyRotatingFileHandler(logging.FileHandler):
    """Обработчик для ротации файлов по дням"""

    def __init__(self, filename_pattern, level=logging.NOTSET, encoding='utf-8'):
        self.filename_pattern = filename_pattern
        self.current_date = datetime.now().date()
        current_filename = self.filename_pattern.format(
            date=self.current_date.strftime('%Y%m%d')
        )
        super().__init__(current_filename, 'a', encoding=encoding)
        # Применяем уровень к файловому обработчику, чтобы он фильтровал по LOG_LEVEL/ERROR_LOG_LEVEL
        self.setLevel(level)

    def emit(self, record):
        """Проверяет, нужно ли сменить файл"""
        current_date = datetime.now().date()
        if current_date != self.current_date:
            self.close()
            self.current_date = current_date
            current_filename = self.filename_pattern.format(
                date=self.current_date.strftime('%Y%m%d')
            )
            self._open()
        super().emit(record)

def setup_logging():
    """Настройка системы логирования"""

    # Определение директории для логов
    env = os.getenv("SERVER_ENV", "dev")
    if env == "prod":
        log_dir = Path("/data/logs")
    else:
        log_dir = Path.cwd() / "data" / "logs"

    # Создание директории, если не существует
    log_dir.mkdir(parents=True, exist_ok=True)

    # Получение уровней логирования из переменных окружения
    log_level_str = os.getenv("LOG_LEVEL", "INFO")
    error_log_level_str = os.getenv("ERROR_LOG_LEVEL", "WARNING")

    # Преобразование строк в уровни логирования
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    error_log_level = getattr(logging, error_log_level_str.upper(), logging.WARNING)

    # Настройка корневого логгера
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Корневой логгер принимает все

    # Очищаем существующие обработчики
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Форматирование логов
    log_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-15s | %(lineno)-3d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Обработчик для обычных логов (ежедневная ротация)
    bot_log_pattern = str(log_dir / "bot_{date}.log")
    bot_handler = DailyRotatingFileHandler(bot_log_pattern, level=log_level)
    bot_handler.setFormatter(log_format)
    root_logger.addHandler(bot_handler)

    # Обработчик для ошибок (ежедневная ротация)
    errors_log_pattern = str(log_dir / "errors_{date}.log")
    errors_handler = DailyRotatingFileHandler(errors_log_pattern, level=error_log_level)
    errors_handler.setFormatter(log_format)
    root_logger.addHandler(errors_handler)

    # Обработчик для вывода в консоль
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(log_format)
    root_logger.addHandler(console_handler)

    # Обработчик для записи в БД
    db_handler = DatabaseHandler(level=logging.DEBUG)
    db_handler.setFormatter(log_format)
    root_logger.addHandler(db_handler)

    # Запускаем асинхронную запись в БД
    db_handler.start()

    # Установка уровня логирования для некоторых модулей
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("aiohttp").setLevel(logging.INFO)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
    logging.getLogger("aiosqlite").setLevel(logging.INFO)

    return db_handler

def setup_logger_with_alerts(bot: Optional[Bot] = None, admin_ids: Optional[List[int]] = None):
    """
    Настройка логгера с поддержкой алертов в Telegram

    Args:
        bot: Экземпляр бота для отправки алертов
        admin_ids: Список ID администраторов для получения алертов
    """
    # Настраиваем базовый логгер
    db_handler = setup_logging()

    # Если переданы параметры для алертов, настраиваем их
    if bot and admin_ids:
        from bot.utils.alerts import setup_alert_handler
        alert_handler = setup_alert_handler(bot, admin_ids)
        return alert_handler, db_handler

    return None, db_handler

async def cleanup_old_logs():
    """Очистка старых логов из файлов и БД"""
    try:
        # Получение настроек из переменных окружения
        log_retention_days = int(os.getenv("LOG_RETENTION_DAYS", "7"))
        db_log_retention_days = int(os.getenv("DB_LOG_RETENTION_DAYS", "30"))

        # Очистка старых файлов логов
        env = os.getenv("SERVER_ENV", "dev")
        if env == "prod":
            log_dir = Path("/data/logs")
        else:
            log_dir = Path.cwd() / "data" / "logs"

        if log_dir.exists():
            cutoff_date = datetime.now() - timedelta(days=log_retention_days)
            for log_file in log_dir.glob("*.log"):
                try:
                    # Пытаемся извлечь дату из имени файла
                    if log_file.name.startswith(("bot_", "errors_")):
                        date_str = log_file.name.split("_")[1].split(".")[0]
                        file_date = datetime.strptime(date_str, "%Y%m%d")
                        if file_date.date() < cutoff_date.date():
                            log_file.unlink()
                            print(f"Удален старый файл лога: {log_file}")
                except (ValueError, IndexError):
                    # Если не удается распарсить дату, пропускаем файл
                    continue

        # Очистка старых записей из БД
        cutoff_timestamp = datetime.now() - timedelta(days=db_log_retention_days)

        async with db.async_session() as session:
            # Удаляем старые записи из application_logs
            result = await session.execute(
                delete(db.ApplicationLog).where(db.ApplicationLog.timestamp < cutoff_timestamp)
            )
            app_logs_deleted = result.rowcount

            # Удаляем старые записи из error_logs
            result = await session.execute(
                delete(db.ErrorLog).where(db.ErrorLog.timestamp < cutoff_timestamp)
            )
            error_logs_deleted = result.rowcount

            await session.commit()

            if app_logs_deleted > 0 or error_logs_deleted > 0:
                print(f"Очищено записей из БД: application_logs={app_logs_deleted}, error_logs={error_logs_deleted}")

    except Exception as e:
        print(f"Ошибка при очистке старых логов: {e}")
