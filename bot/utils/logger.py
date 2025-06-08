import logging
import os
import sys
from pathlib import Path
import aiogram
from typing import Optional, List
from aiogram import Bot

def setup_logger():
    # Определение директории для логов
    env = os.getenv("SERVER_ENV", "dev")
    if env == "prod":
        log_dir = Path("/data/logs")
    else:
        log_dir = Path.cwd() / "data" / "logs"

    # Создание директории, если не существует
    log_dir.mkdir(parents=True, exist_ok=True)

    # Определение пути к файлу лога
    log_file = log_dir / "bot.log"

    # Настройка корневого логгера
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Форматирование логов
    log_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Настройка файлового обработчика
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(log_format)
    root_logger.addHandler(file_handler)

    # Настройка вывода в консоль
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    root_logger.addHandler(console_handler)

    # Установка уровня логирования для некоторых модулей
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("aiohttp").setLevel(logging.INFO)
    logging.getLogger("apscheduler").setLevel(logging.INFO)

def setup_logger_with_alerts(bot: Optional[Bot] = None, admin_ids: Optional[List[int]] = None):
    """
    Настройка логгера с поддержкой алертов в Telegram

    Args:
        bot: Экземпляр бота для отправки алертов
        admin_ids: Список ID администраторов для получения алертов
    """
    # Сначала настраиваем базовый логгер
    setup_logger()

    # Если переданы параметры для алертов, настраиваем их
    if bot and admin_ids:
        from bot.utils.alerts import setup_alert_handler
        alert_handler = setup_alert_handler(bot, admin_ids)
        return alert_handler

    return None
