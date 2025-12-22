"""
Сервис напоминаний о непроверенных ответах студентов

Анализирует ответы студентов за определенную дату и создает
напоминания для менторов
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import defaultdict

import pytz
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.database import (
    get_session, WebhookEvent, Mentor, Student, Training, Mapping, Notification
)
from bot.services.notification_calculator import NotificationCalculationService

logger = logging.getLogger(__name__)


class ReminderService:
    """Сервис обработки напоминаний о непроверенных ответах"""

    def __init__(self, config):
        self.config = config
        self.notification_calculator = NotificationCalculationService(config)
        self.moscow_tz = pytz.timezone('Europe/Moscow')

    async def process_reminder_notifications(self, analysis_date: Optional[datetime] = None):
        """
        Главный метод обработки напоминаний

        Миграция логики из reminderHandlers.gs:9-108

        Args:
            analysis_date: Дата для анализа (по умолчанию 2 дня назад)
        """
        try:
            # 1. Определить дату анализа
            if not analysis_date:
                days_back = self.config.reminder_analysis_days_back
                analysis_date = datetime.now(pytz.UTC) - timedelta(days=days_back)

            # Приводим к началу дня
            analysis_date = analysis_date.replace(hour=0, minute=0, second=0, microsecond=0)

            logger.info(f"Обработка напоминаний для даты: {analysis_date.date()}")

            async for session in get_session():
                # 2. Получить ответы студентов за эту дату
                relevant_answers = await self.get_answers_for_date(
                    session,
                    analysis_date
                )

                if not relevant_answers:
                    logger.info(
                        f"Нет ответов студентов за {analysis_date.date()}. "
                        "Напоминания не требуются."
                    )
                    return

                logger.info(f"Найдено {len(relevant_answers)} ответов за {analysis_date.date()}")

                # 3. Сгруппировать по наставникам
                mentor_groups = await self.group_answers_by_mentor(
                    session,
                    relevant_answers
                )

                if not mentor_groups:
                    logger.info("Не удалось сгруппировать ответы по наставникам")
                    return

                # 4. Создать напоминания для каждого ментора
                reminders_created = 0

                for mentor_id, students in mentor_groups.items():
                    try:
                        # Сортировка по времени ответа
                        students.sort(key=lambda s: s.get('webhook_date', datetime.min))

                        # Формирование сообщения
                        message = self.notification_calculator.format_reminder_notification(
                            students=students
                        )

                        # Создание уведомления
                        notification = Notification(
                            mentor_id=mentor_id,
                            type='reminderUncheckedAnswers',
                            message=message,
                            status='pending',
                            created_at=datetime.now(pytz.UTC)
                        )

                        session.add(notification)
                        reminders_created += 1

                        mentor = await session.get(Mentor, mentor_id)
                        mentor_name = f"{mentor.first_name or ''} {mentor.last_name or ''}".strip() if mentor else str(mentor_id)

                        logger.info(
                            f"Создано напоминание для наставника {mentor_name} ({mentor_id}), "
                            f"студентов: {len(students)}"
                        )

                    except Exception as e:
                        logger.error(
                            f"Ошибка при создании напоминания для ментора {mentor_id}: {e}",
                            exc_info=True
                        )
                        continue

                # Коммитим все изменения
                await session.commit()

                logger.info(
                    f"Обработка напоминаний завершена. "
                    f"Создано напоминаний: {reminders_created}"
                )

        except Exception as e:
            logger.error(f"Критическая ошибка при обработке напоминаний: {e}", exc_info=True)

    async def get_answers_for_date(
        self,
        session: AsyncSession,
        target_date: datetime
    ) -> List[Dict]:
        """
        Получение ответов студентов за определенную дату

        Args:
            session: Сессия БД
            target_date: Дата для анализа

        Returns:
            Список словарей с данными ответов
        """
        try:
            # Определяем диапазон дат (весь день)
            start_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=1)

            # Запрос к webhook_events
            query = select(WebhookEvent).where(
                and_(
                    WebhookEvent.event_date >= start_date,
                    WebhookEvent.event_date < end_date,
                    WebhookEvent.answer_status == 'new'
                )
            ).order_by(WebhookEvent.event_date)

            result = await session.execute(query)
            webhooks = result.scalars().all()

            # Формируем список ответов
            answers = []
            for webhook in webhooks:
                answers.append({
                    'row': webhook.id,
                    'user_id': webhook.user_id,
                    'user_email': webhook.user_email,
                    'first_name': webhook.user_first_name or '',
                    'last_name': webhook.user_last_name or '',
                    'answer_id': webhook.answer_id,
                    'answer_training_id': webhook.answer_training_id,
                    'answer_lesson_id': webhook.answer_lesson_id,
                    'answer_text': webhook.answer_text,
                    'webhook_date': webhook.event_date
                })

            return answers

        except Exception as e:
            logger.error(f"Ошибка при получении ответов за дату: {e}", exc_info=True)
            return []

    async def group_answers_by_mentor(
        self,
        session: AsyncSession,
        answers: List[Dict]
    ) -> Dict[int, List[Dict]]:
        """
        Группировка ответов по наставникам

        Args:
            session: Сессия БД
            answers: Список ответов студентов

        Returns:
            Словарь {mentor_id: [список студентов с ответами]}
        """
        try:
            mentor_groups = defaultdict(list)

            for answer in answers:
                # Находим наставника для этого студента и тренинга
                mentor_id = await self._find_mentor_for_answer(
                    session,
                    answer['user_id'],
                    answer['answer_training_id']
                )

                if mentor_id:
                    mentor_groups[mentor_id].append(answer)
                else:
                    logger.warning(
                        f"Не найден наставник для студента {answer['user_id']} "
                        f"в тренинге {answer['answer_training_id']}"
                    )

            return dict(mentor_groups)

        except Exception as e:
            logger.error(f"Ошибка при группировке ответов: {e}", exc_info=True)
            return {}

    async def _find_mentor_for_answer(
        self,
        session: AsyncSession,
        student_getcourse_id: int,
        training_getcourse_id: str
    ) -> Optional[int]:
        """
        Поиск ID ментора для студента в тренинге

        Args:
            session: Сессия БД
            student_getcourse_id: GetCourse ID студента
            training_getcourse_id: GetCourse ID тренинга

        Returns:
            ID ментора (из таблицы mentors) или None
        """
        try:
            # Находим студента
            student_query = select(Student).where(
                Student.student_id == student_getcourse_id,
                Student.valid_to == datetime(9999, 12, 31, tzinfo=pytz.UTC)
            )
            student_result = await session.execute(student_query)
            student = student_result.scalars().first()

            if not student:
                return None

            # Находим тренинг
            training_query = select(Training).where(
                Training.training_id == training_getcourse_id,
                Training.valid_to == datetime(9999, 12, 31, tzinfo=pytz.UTC)
            )
            training_result = await session.execute(training_query)
            training = training_result.scalars().first()

            if not training:
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

            if mapping:
                return mapping.mentor_id

            return None

        except Exception as e:
            logger.error(f"Ошибка при поиске ментора: {e}", exc_info=True)
            return None


