import asyncio
import logging
from datetime import datetime
from typing import Dict, List

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.api import get_new_notifications, update_notification_status, GoogleScriptError, ApiError
from bot.services.database import get_session, Mentor, Notification
from bot.config import Config
from bot.utils.markdown import escape_markdown_v2, format_notification, format_student_action, convert_pseudo_markdown_to_v2
from bot.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

async def check_new_notifications(bot: Bot, config: Config):
    """
    Проверяет наличие новых уведомлений и отправляет их менторам.

    Args:
        bot: Экземпляр бота Telegram
        config: Конфигурация бота
    """
    try:
        # Получение новых уведомлений из API
        notifications = await get_new_notifications(config.api_url, limit=20, config=config)

        if not notifications:
            return

        logger.info(f"Получено {len(notifications)} новых уведомлений")

        # Обработка каждого уведомления
        for notification in notifications:
            await process_notification(bot, config, notification)

            # Небольшая задержка между отправками для избежания флуда
            await asyncio.sleep(0.5)

    except GoogleScriptError as e:
        logger.error(f"Ошибка Google Script при проверке новых уведомлений: {e}")
        if e.html_content:
            logger.error(f"HTML ответ от Google Script: {e.html_content[:500]}")
    except ApiError as e:
        logger.error(f"Ошибка API при проверке новых уведомлений: {e}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка при проверке новых уведомлений: {e}")
        logger.exception("Полный traceback:")

async def _send_notification_with_retry(bot: Bot, telegram_id: int, formatted_message: str) -> int:
    """
    Отправляет уведомление с повторными попытками.

    Args:
        bot: Экземпляр бота Telegram
        telegram_id: ID чата для отправки
        formatted_message: Отформатированное сообщение

    Returns:
        ID отправленного сообщения

    Raises:
        Exception: Если все попытки отправки не удались
    """
    async def _send_message():
        message = await bot.send_message(
            chat_id=telegram_id,
            text=formatted_message,
            parse_mode="MarkdownV2"
        )
        return message.message_id

    return await _send_message()


async def process_notification(bot: Bot, config: Config, notification: Dict):
    """
    Обрабатывает одно уведомление с повторными попытками отправки.

    Args:
        bot: Экземпляр бота Telegram
        config: Конфигурация бота
        notification: Данные уведомления
    """
    telegram_id = notification.get("telegramId")
    notification_id = notification.get("id")
    notification_type = notification.get("type", "unknown")

    if not telegram_id or not notification_id:
        logger.warning(f"Некорректные данные уведомления: {notification}")
        return

    try:
        # Форматирование сообщения
        formatted_message = format_notification_message(notification)

        # Отправка уведомления в Telegram с повторными попытками
        message_id = await retry_with_backoff(
            func=lambda: _send_notification_with_retry(bot, telegram_id, formatted_message),
            max_retries=config.notification_max_retries,
            base_delay=config.notification_retry_base_delay,
            max_delay=config.notification_retry_max_delay,
            exponential_base=2.0,
            jitter=True,
            retry_exceptions=[Exception]  # Повторяем при любых ошибках сети/API
        )

        # Обновление статуса уведомления
        await update_notification_status(
            config.api_url,
            notification_id,
            "sent",
            message_id,
            config
        )

        # Сохранение в локальной БД
        async for session in get_session():
            await save_notification_to_db(session, notification, "sent", message_id)

        logger.info(f"Уведомление {notification_id} успешно отправлено ментору {telegram_id}")

        # Возвращаемся из функции после успешной отправки
        return

    except GoogleScriptError as e:
        logger.error(f"Ошибка Google Script при отправке уведомления {notification_id}: {e}")
        if e.html_content:
            logger.error(f"HTML ответ от Google Script: {e.html_content[:500]}")
    except ApiError as e:
        logger.error(f"Ошибка API при отправке уведомления {notification_id}: {e}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка при отправке уведомления {notification_id}: {e}")
        logger.exception("Полный traceback:")

    # Обновление статуса на "failed" в случае любой ошибки после всех попыток
    try:
        await update_notification_status(config.api_url, notification_id, "failed", config=config)

        # Сохранение в локальной БД
        async for session in get_session():
            await save_notification_to_db(session, notification, "failed")

    except GoogleScriptError as e2:
        logger.error(f"Ошибка Google Script при обновлении статуса уведомления {notification_id}: {e2}")
    except ApiError as e2:
        logger.error(f"Ошибка API при обновлении статуса уведомления {notification_id}: {e2}")
    except Exception as e2:
        logger.error(f"Неожиданная ошибка при обновлении статуса уведомления {notification_id}: {e2}")
        logger.exception("Полный traceback при обновлении статуса:")

async def save_notification_to_db(session: AsyncSession, notification: Dict, status: str, message_id: int = None):
    """
    Сохраняет историю уведомления в локальной базе данных.

    Args:
        session: Сессия базы данных
        notification: Данные уведомления
        status: Статус отправки
        message_id: ID сообщения в Telegram
    """
    try:
        db_notification = Notification(
            mentor_id=notification.get("recipientId"),
            type=notification.get("type", "unknown"),
            message=notification.get("message", ""),
            status=status,
            sent_at=datetime.now() if status == "sent" else None
        )

        session.add(db_notification)
        await session.commit()

    except Exception as e:
        logger.error(f"Ошибка при сохранении уведомления в БД: {e}")
        await session.rollback()

def format_notification_message(notification: Dict) -> str:
    """
    Форматирует сообщение уведомления с использованием MarkdownV2.

    Args:
        notification: Данные уведомления

    Returns:
        Отформатированное сообщение
    """
    message = notification.get("message", "")

    if not message:
        return "Пустое уведомление"

    # Если сообщение содержит псевдо-markdown (звездочки и ссылки), конвертируем его
    if "*" in message or "[" in message:
        return convert_pseudo_markdown_to_v2(message)

    # Если обычный текст, просто экранируем
    return escape_markdown_v2(message)
