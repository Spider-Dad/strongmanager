"""
Сервис отправки уведомлений в Telegram

Читает pending уведомления из таблицы notifications
и отправляет их менторам через Telegram Bot API
"""

import logging
from datetime import datetime
from typing import Optional

import pytz
from aiogram import Bot
from aiogram.utils.exceptions import TelegramAPIError
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.database import get_session, Notification, Mentor
from bot.utils.retry import retry_with_backoff
from bot.utils.markdown import convert_pseudo_markdown_to_v2

logger = logging.getLogger(__name__)


class NotificationSenderService:
    """Сервис отправки уведомлений в Telegram"""

    def __init__(self, config, bot: Bot):
        self.config = config
        self.bot = bot

    async def send_pending_notifications(self):
        """
        Главный метод отправки необработанных уведомлений

        Читает уведомления со статусом 'pending' и отправляет их
        """
        try:
            async for session in get_session():
                # Получаем pending уведомления (батчами)
                batch_size = self.config.notification_batch_size

                query = select(Notification).where(
                    Notification.status == 'pending'
                ).order_by(Notification.created_at).limit(batch_size)

                result = await session.execute(query)
                notifications = result.scalars().all()

                if not notifications:
                    logger.debug("Нет pending уведомлений")
                    return

                logger.info(f"Найдено {len(notifications)} pending уведомлений")

                # Обрабатываем каждое уведомление
                sent_count = 0
                failed_count = 0
                no_telegram_count = 0

                for notification in notifications:
                    try:
                        # Получаем ментора
                        mentor = await self.get_mentor_by_id(session, notification.mentor_id)

                        if not mentor:
                            logger.warning(
                                f"Ментор {notification.mentor_id} не найден "
                                f"для уведомления {notification.id}"
                            )
                            notification.status = 'failed'
                            failed_count += 1
                            continue

                        if not mentor.telegram_id:
                            logger.info(
                                f"У ментора {notification.mentor_id} нет telegram_id. "
                                f"Уведомление {notification.id} отложено."
                            )
                            notification.status = 'no_telegram_id'
                            no_telegram_count += 1
                            continue

                        # Отправляем уведомление в Telegram
                        message_id = await self.send_notification_to_telegram(
                            telegram_id=mentor.telegram_id,
                            message=notification.message
                        )

                        # Обновляем статус
                        notification.status = 'sent'
                        notification.sent_at = datetime.now(pytz.UTC)
                        notification.telegram_message_id = message_id
                        sent_count += 1

                        logger.info(
                            f"Уведомление {notification.id} отправлено "
                            f"ментору {mentor.email} (TG: {mentor.telegram_id})"
                        )

                        # Небольшая задержка между отправками
                        import asyncio
                        await asyncio.sleep(0.5)

                    except TelegramAPIError as e:
                        logger.error(
                            f"Ошибка Telegram API при отправке уведомления {notification.id}: {e}",
                            exc_info=True
                        )
                        notification.status = 'failed'
                        failed_count += 1

                    except Exception as e:
                        logger.error(
                            f"Ошибка при отправке уведомления {notification.id}: {e}",
                            exc_info=True
                        )
                        notification.status = 'failed'
                        failed_count += 1

                # Коммитим все изменения
                await session.commit()

                logger.info(
                    f"Отправка завершена: отправлено={sent_count}, "
                    f"ошибок={failed_count}, без telegram_id={no_telegram_count}"
                )

        except Exception as e:
            logger.error(f"Критическая ошибка при отправке уведомлений: {e}", exc_info=True)

    async def get_mentor_by_id(
        self,
        session: AsyncSession,
        mentor_id: int
    ) -> Optional[Mentor]:
        """
        Получение ментора по ID

        Args:
            session: Сессия БД
            mentor_id: ID ментора (BIGINT из таблицы mentors)

        Returns:
            Объект Mentor или None
        """
        try:
            query = select(Mentor).where(
                and_(
                    Mentor.id == mentor_id,
                    Mentor.valid_to == datetime(9999, 12, 31, tzinfo=pytz.UTC)
                )
            )
            result = await session.execute(query)
            return result.scalars().first()

        except Exception as e:
            logger.error(f"Ошибка при получении ментора: {e}", exc_info=True)
            return None

    async def send_notification_to_telegram(
        self,
        telegram_id: int,
        message: str
    ) -> int:
        """
        Отправка уведомления в Telegram с повторными попытками

        Args:
            telegram_id: Telegram ID пользователя
            message: Текст сообщения

        Returns:
            ID отправленного сообщения
        """
        async def _send():
            # Конвертируем псевдо-markdown в MarkdownV2
            formatted_message = convert_pseudo_markdown_to_v2(message)

            # Отправляем сообщение
            sent_message = await self.bot.send_message(
                chat_id=telegram_id,
                text=formatted_message,
                parse_mode="MarkdownV2"
            )

            return sent_message.message_id

        # Отправка с retry
        return await retry_with_backoff(
            func=_send,
            max_retries=self.config.notification_max_retries,
            base_delay=self.config.notification_retry_base_delay,
            max_delay=self.config.notification_retry_max_delay,
            exponential_base=2.0,
            jitter=True,
            retry_exceptions=[TelegramAPIError]
        )