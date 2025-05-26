import logging
import os
import sys
from pathlib import Path
import aiogram

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
