import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from aiogram import Bot
from aiogram.utils.exceptions import TelegramAPIError
import traceback


class AlertHandler(logging.Handler):
    """Обработчик логов для отправки алертов в Telegram"""

    def __init__(self, bot: Bot, admin_ids: List[int], alert_interval: int = 300, error_collector=None):
        """
        Инициализация обработчика алертов

        Args:
            bot: Экземпляр бота для отправки сообщений
            admin_ids: Список ID администраторов для получения алертов
            alert_interval: Минимальный интервал между алертами одного типа (в секундах)
            error_collector: Коллектор ошибок для сохранения истории
        """
        super().__init__()
        self.bot = bot
        self.admin_ids = admin_ids
        self.alert_interval = alert_interval
        self.last_alerts: Dict[str, datetime] = {}
        self.alert_queue = asyncio.Queue()
        self.worker_task: Optional[asyncio.Task] = None
        self.error_collector = error_collector

    def start(self):
        """Запуск воркера для обработки алертов"""
        if not self.worker_task or self.worker_task.done():
            self.worker_task = asyncio.create_task(self._alert_worker())

    def stop(self):
        """Остановка воркера"""
        if self.worker_task and not self.worker_task.done():
            self.worker_task.cancel()

    async def _alert_worker(self):
        """Воркер для асинхронной отправки алертов"""
        while True:
            try:
                alert_data = await self.alert_queue.get()
                await self._send_alert(**alert_data)
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Логируем ошибку отправки алерта, но не создаем новый алерт
                print(f"Ошибка при отправке алерта: {e}")

    def emit(self, record: logging.LogRecord):
        """Обработка записи лога"""
        if record.levelno >= logging.ERROR:
            # Проверяем, не слишком ли часто отправляем алерты одного типа
            error_key = f"{record.name}:{record.msg[:100]}"
            now = datetime.now()

            if error_key in self.last_alerts:
                if now - self.last_alerts[error_key] < timedelta(seconds=self.alert_interval):
                    return

            self.last_alerts[error_key] = now

            # Добавляем алерт в очередь
            alert_data = {
                'level': record.levelname,
                'logger_name': record.name,
                'message': record.getMessage(),
                'timestamp': datetime.fromtimestamp(record.created),
                'traceback': self.format(record) if record.exc_info else None
            }

            # Сохраняем ошибку в коллектор, если он есть
            if self.error_collector:
                self.error_collector.add_error(alert_data)

            try:
                self.alert_queue.put_nowait(alert_data)
            except asyncio.QueueFull:
                # Если очередь переполнена, пропускаем алерт
                pass

    async def _send_alert(self, level: str, logger_name: str, message: str,
                         timestamp: datetime, traceback: Optional[str] = None):
        """Отправка алерта администраторам"""
        # Форматирование сообщения
        alert_text = f"""
🚨 *АЛЕРТ: {level}*

📅 *Время:* {timestamp.strftime('%Y-%m-%d %H:%M:%S')}
📍 *Модуль:* `{logger_name}`

💬 *Сообщение:*
```
{message[:1000]}
```
"""

        if traceback:
            alert_text += f"\n📋 *Traceback:*\n```\n{traceback[:2000]}\n```"

        # Отправка сообщения всем администраторам
        for admin_id in self.admin_ids:
            try:
                await self.bot.send_message(
                    admin_id,
                    alert_text,
                    parse_mode="Markdown",
                    disable_notification=False
                )
            except TelegramAPIError as e:
                print(f"Не удалось отправить алерт администратору {admin_id}: {e}")


class ErrorCollector:
    """Класс для сбора и группировки ошибок"""

    def __init__(self, max_errors: int = 10):
        self.errors = []
        self.max_errors = max_errors

    def add_error(self, error_data: Dict[str, Any]):
        """Добавление ошибки в коллектор"""
        self.errors.append(error_data)
        if len(self.errors) > self.max_errors:
            self.errors.pop(0)

    def get_summary(self) -> str:
        """Получение сводки по ошибкам"""
        if not self.errors:
            return "Ошибок не обнаружено"

        summary = f"Всего ошибок: {len(self.errors)}\n\n"

        for i, error in enumerate(self.errors[-5:], 1):  # Последние 5 ошибок
            summary += f"{i}. [{error['timestamp']}] {error['level']} - {error['message'][:100]}...\n"

        return summary


def setup_alert_handler(bot: Bot, admin_ids: List[int], logger: Optional[logging.Logger] = None) -> AlertHandler:
    """
    Настройка обработчика алертов для логгера

    Args:
        bot: Экземпляр бота
        admin_ids: Список ID администраторов
        logger: Логгер для добавления обработчика (если None, используется корневой)

    Returns:
        AlertHandler: Настроенный обработчик алертов
    """
    if not logger:
        logger = logging.getLogger()

    # Импортируем error_collector из admin.py
    try:
        from bot.handlers.admin import error_collector
    except ImportError:
        error_collector = None

    # Создаем обработчик алертов
    alert_handler = AlertHandler(bot, admin_ids, error_collector=error_collector)
    alert_handler.setLevel(logging.ERROR)

    # Добавляем форматтер
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s\n%(exc_info)s"
    )
    alert_handler.setFormatter(formatter)

    # Добавляем обработчик к логгеру
    logger.addHandler(alert_handler)

    # Запускаем воркер
    alert_handler.start()

    return alert_handler