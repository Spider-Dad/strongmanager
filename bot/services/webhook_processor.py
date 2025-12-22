"""
Сервис обработки вебхуков из GetCourse

Читает необработанные записи из таблицы webhook_events
и создает уведомления для менторов
"""

import logging
from datetime import datetime
from typing import Optional, Dict

import pytz
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.database import (
    get_session, WebhookEvent, Notification, Mentor, Student,
    Training, Lesson, Mapping
)
from bot.services.notification_calculator import NotificationCalculationService

logger = logging.getLogger(__name__)


class WebhookProcessingService:
    """Сервис обработки вебхуков от GetCourse"""

    def __init__(self, config):
        self.config = config
        self.notification_calculator = NotificationCalculationService(config)
        self.moscow_tz = pytz.timezone('Europe/Moscow')

    async def process_pending_webhooks(self):
        """
        Главный метод обработки необработанных вебхуков

        Читает записи с processed = false и обрабатывает их
        """
        try:
            async for session in get_session():
                # Получаем необработанные вебхуки (батчами)
                batch_size = self.config.webhook_batch_size

                query = select(WebhookEvent).where(
                    WebhookEvent.processed == False
                ).order_by(WebhookEvent.created_at).limit(batch_size)

                result = await session.execute(query)
                webhooks = result.scalars().all()

                if not webhooks:
                    logger.debug("Нет необработанных вебхуков")
                    return

                logger.info(f"Найдено {len(webhooks)} необработанных вебхуков")

                # Обрабатываем каждый вебхук
                processed_count = 0
                error_count = 0

                for webhook in webhooks:
                    try:
                        # Определяем тип события и обрабатываем
                        if webhook.answer_status and webhook.answer_status.lower() in ['new', 'accepted']:
                            await self.process_answer_to_lesson(session, webhook)
                            processed_count += 1
                        else:
                            logger.warning(
                                f"Неизвестный статус ответа: {webhook.answer_status} "
                                f"для webhook {webhook.id}"
                            )

                        # Помечаем вебхук как обработанный
                        webhook.processed = True
                        webhook.processed_at = datetime.now(pytz.UTC)

                    except Exception as e:
                        logger.error(f"Ошибка обработки webhook {webhook.id}: {e}", exc_info=True)
                        webhook.error_message = str(e)[:500]  # Сохраняем ошибку
                        error_count += 1

                # Коммитим все изменения
                await session.commit()

                logger.info(
                    f"Обработка завершена: успешно={processed_count}, "
                    f"ошибок={error_count}"
                )

        except Exception as e:
            logger.error(f"Критическая ошибка при обработке вебхуков: {e}", exc_info=True)

    async def process_answer_to_lesson(
        self,
        session: AsyncSession,
        webhook_event: WebhookEvent
    ):
        """
        Обработка ответа на урок

        Миграция логики из lessonHandlers.gs:16-105

        Args:
            session: Сессия БД
            webhook_event: Событие вебхука
        """
        # 1. Найти наставника для этого студента и тренинга
        mentor = await self.find_mentor_for_student(
            session,
            webhook_event.user_id,
            webhook_event.answer_training_id
        )

        if not mentor:
            logger.warning(
                f"Не найден наставник для студента {webhook_event.user_id} "
                f"в тренинге {webhook_event.answer_training_id}"
            )
            return

        # 2. Получить информацию об уроке
        lesson = await self.get_lesson_info(session, webhook_event.answer_lesson_id)

        if not lesson:
            logger.warning(f"Не найден урок {webhook_event.answer_lesson_id}")
            return

        # 3. Получить информацию о тренинге
        training = await self.get_training_info(session, webhook_event.answer_training_id)

        if not training:
            logger.warning(f"Не найден тренинг {webhook_event.answer_training_id}")
            return

        # 4. Сформировать сообщение
        student_name = f"{webhook_event.user_first_name or ''} {webhook_event.user_last_name or ''}".strip()

        message = self.notification_calculator.format_answer_notification(
            student_name=student_name,
            student_email=webhook_event.user_email,
            training_title=training.title,
            module_number=lesson.module_number,
            lesson_title=lesson.lesson_title,
            user_id=webhook_event.user_id
        )

        # 5. Создать уведомление
        await self.create_notification(
            session,
            mentor_id=mentor.id,
            notification_type='answerToLesson',
            message=message
        )

        logger.info(
            f"Создано уведомление для ментора {mentor.id} "
            f"о новом ответе студента {student_name}"
        )

    async def find_mentor_for_student(
        self,
        session: AsyncSession,
        student_getcourse_id: int,
        training_getcourse_id: str
    ) -> Optional[Mentor]:
        """
        Поиск наставника для студента в конкретном тренинге

        Args:
            session: Сессия БД
            student_getcourse_id: ID студента из GetCourse
            training_getcourse_id: ID тренинга из GetCourse

        Returns:
            Объект Mentor или None
        """
        try:
            # Находим студента по GetCourse ID
            student_query = select(Student).where(
                Student.student_id == student_getcourse_id,
                Student.valid_to == datetime(9999, 12, 31, tzinfo=pytz.UTC)
            )
            student_result = await session.execute(student_query)
            student = student_result.scalars().first()

            if not student:
                logger.warning(f"Студент с GetCourse ID {student_getcourse_id} не найден")
                return None

            # Находим тренинг по GetCourse ID
            training_query = select(Training).where(
                Training.training_id == training_getcourse_id,
                Training.valid_to == datetime(9999, 12, 31, tzinfo=pytz.UTC)
            )
            training_result = await session.execute(training_query)
            training = training_result.scalars().first()

            if not training:
                logger.warning(f"Тренинг {training_getcourse_id} не найден")
                return None

            # Находим mapping
            mapping_query = select(Mapping).where(
                and_(
                    Mapping.student_id == student.id,
                    Mapping.training_id == training.id,
                    Mapping.valid_to == datetime(9999, 12, 31, tzinfo=pytz.UTC)
                )
            )
            mapping_result = await session.execute(mapping_query)
            mapping = mapping_result.scalars().first()

            if not mapping:
                logger.warning(
                    f"Mapping не найден для студента {student.id} "
                    f"и тренинга {training.id}"
                )
                return None

            # Находим ментора
            mentor_query = select(Mentor).where(
                and_(
                    Mentor.id == mapping.mentor_id,
                    Mentor.valid_to == datetime(9999, 12, 31, tzinfo=pytz.UTC)
                )
            )
            mentor_result = await session.execute(mentor_query)
            mentor = mentor_result.scalars().first()

            return mentor

        except Exception as e:
            logger.error(f"Ошибка при поиске ментора: {e}", exc_info=True)
            return None

    async def get_lesson_info(
        self,
        session: AsyncSession,
        lesson_getcourse_id: str
    ) -> Optional[Lesson]:
        """
        Получение информации об уроке

        Args:
            session: Сессия БД
            lesson_getcourse_id: ID урока из GetCourse

        Returns:
            Объект Lesson или None
        """
        try:
            query = select(Lesson).where(
                Lesson.lesson_id == lesson_getcourse_id,
                Lesson.valid_to == datetime(9999, 12, 31, tzinfo=pytz.UTC)
            )
            result = await session.execute(query)
            return result.scalars().first()

        except Exception as e:
            logger.error(f"Ошибка при получении урока: {e}", exc_info=True)
            return None

    async def get_training_info(
        self,
        session: AsyncSession,
        training_getcourse_id: str
    ) -> Optional[Training]:
        """
        Получение информации о тренинге

        Args:
            session: Сессия БД
            training_getcourse_id: ID тренинга из GetCourse

        Returns:
            Объект Training или None
        """
        try:
            query = select(Training).where(
                Training.training_id == training_getcourse_id,
                Training.valid_to == datetime(9999, 12, 31, tzinfo=pytz.UTC)
            )
            result = await session.execute(query)
            return result.scalars().first()

        except Exception as e:
            logger.error(f"Ошибка при получении тренинга: {e}", exc_info=True)
            return None

    async def create_notification(
        self,
        session: AsyncSession,
        mentor_id: int,
        notification_type: str,
        message: str
    ):
        """
        Создание уведомления в таблице notifications

        Args:
            session: Сессия БД
            mentor_id: ID ментора (BIGINT из таблицы mentors)
            notification_type: Тип уведомления
            message: Текст сообщения
        """
        try:
            notification = Notification(
                mentor_id=mentor_id,
                type=notification_type,
                message=message,
                status='pending',
                created_at=datetime.now(pytz.UTC)
            )

            session.add(notification)
            # Не коммитим здесь - коммит будет в основном методе

        except Exception as e:
            logger.error(f"Ошибка при создании уведомления: {e}", exc_info=True)
            raise


