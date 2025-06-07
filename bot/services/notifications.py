import asyncio
import logging
from datetime import datetime
from typing import Dict, List

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.api import get_new_notifications, update_notification_status
from bot.services.database import get_session, Mentor, Notification
from bot.config import Config
from bot.utils.markdown import escape_markdown_v2, format_notification, format_student_action

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
        notifications = await get_new_notifications(config.api_url, limit=20)

        if not notifications:
            return

        logger.info(f"Получено {len(notifications)} новых уведомлений")

        # Обработка каждого уведомления
        for notification in notifications:
            await process_notification(bot, config, notification)

            # Небольшая задержка между отправками для избежания флуда
            await asyncio.sleep(0.5)

    except Exception as e:
        logger.error(f"Ошибка при проверке новых уведомлений: {e}")

async def process_notification(bot: Bot, config: Config, notification: Dict):
    """
    Обрабатывает одно уведомление.

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

        # Отправка уведомления в Telegram
        message = await bot.send_message(
            chat_id=telegram_id,
            text=formatted_message,
            parse_mode="MarkdownV2"
        )

        # Обновление статуса уведомления
        await update_notification_status(
            config.api_url,
            notification_id,
            "sent",
            message.message_id
        )

        # Сохранение в локальной БД
        async for session in get_session():
            await save_notification_to_db(session, notification, "sent", message.message_id)

        logger.info(f"Уведомление {notification_id} успешно отправлено ментору {telegram_id}")

    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления {notification_id}: {e}")

        # Обновление статуса на "failed"
        try:
            await update_notification_status(config.api_url, notification_id, "failed")

            # Сохранение в локальной БД
            async for session in get_session():
                await save_notification_to_db(session, notification, "failed")

        except Exception as e2:
            logger.error(f"Не удалось обновить статус уведомления {notification_id}: {e2}")

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
    notification_type = notification.get("type", "unknown")
    message = notification.get("message", "")

    # Если сообщение уже отформатировано, возвращаем как есть
    if message.startswith("*") or message.startswith("_"):
        return message

    # Базовое форматирование для разных типов уведомлений
    if notification_type == "student_answer":
        student_name = notification.get("studentName", "Неизвестный студент")
        task_name = notification.get("taskName", "Неизвестное задание")
        url = notification.get("url")
        return format_student_action(student_name, "отправил ответ на задание", task_name, url)

    elif notification_type == "student_comment":
        student_name = notification.get("studentName", "Неизвестный студент")
        task_name = notification.get("taskName", "Неизвестное задание")
        url = notification.get("url")
        return format_student_action(student_name, "оставил комментарий к заданию", task_name, url)

    elif notification_type == "task_deadline":
        task_name = notification.get("taskName", "Неизвестное задание")
        deadline = notification.get("deadline", "")
        url = notification.get("url")
        return format_notification(
            "⏰ Приближается дедлайн",
            f"Задание: {task_name}\nДедлайн: {deadline}",
            url
        )

    else:
        # Для остальных типов уведомлений просто экранируем текст
        return escape_markdown_v2(message)
