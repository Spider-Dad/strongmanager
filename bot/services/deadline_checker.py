"""
Сервис проверки приближающихся дедлайнов

Проверяет уроки с приближающимися дедлайнами и создает уведомления
для менторов о студентах без ответов
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict
from collections import defaultdict

import pytz
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.database import (
    get_session, Lesson, Training, Student, Mapping,
    WebhookEvent, Notification
)
from bot.services.notification_calculator import NotificationCalculationService

logger = logging.getLogger(__name__)


class DeadlineCheckService:
    """Сервис проверки приближающихся дедлайнов"""

    def __init__(self, config):
        self.config = config
        self.notification_calculator = NotificationCalculationService(config)
        self.moscow_tz = pytz.timezone('Europe/Moscow')

    async def check_deadlines(self):
        """
        Главный метод проверки дедлайнов

        Миграция логики из deadlineHandlers.gs:9-182
        """
        try:
            logger.info("Запуск проверки приближающихся дедлайнов")

            async for session in get_session():
                # 1. Получить текущее время в UTC
                now_utc = datetime.now(pytz.UTC)

                # 2. Получить уроки с приближающимися дедлайнами
                approaching_lessons = await self.get_approaching_deadlines(
                    session,
                    now_utc
                )

                if not approaching_lessons:
                    logger.info("Нет приближающихся дедлайнов")
                    return

                logger.info(f"Найдено {len(approaching_lessons)} уроков с приближающимися дедлайнами")

                notifications_created = 0

                # 3. Обработать каждый урок
                for lesson in approaching_lessons:
                    try:
                        # Получить студентов без ответов
                        students_without_answers = await self.get_students_without_answers(
                            session,
                            lesson.lesson_id
                        )

                        if not students_without_answers:
                            continue

                        # Сгруппировать студентов по наставникам
                        mentor_groups = await self.group_students_by_mentor(
                            session,
                            students_without_answers,
                            lesson.training_id
                        )

                        # Создать уведомления для каждого ментора
                        for mentor_id, students in mentor_groups.items():
                            # Проверить дубликаты для каждого студента
                            filtered_students = []
                            for student in students:
                                is_duplicate = await self.notification_calculator.check_duplicate_notification(
                                    session,
                                    mentor_id=mentor_id,
                                    notification_type='deadlineApproaching',
                                    lesson_title=lesson.lesson_title,
                                    student_name=f"{student['first_name']} {student['last_name']}",
                                    deadline_date=lesson.deadline_date
                                )

                                if not is_duplicate:
                                    filtered_students.append(student)
                                else:
                                    logger.debug(
                                        f"Пропущен дубликат для ментора {mentor_id}, "
                                        f"студент {student['first_name']} {student['last_name']}"
                                    )

                            # Создать уведомление если есть студенты
                            if filtered_students:
                                # Получить training для названия
                                training = await session.get(Training, lesson.training_id)

                                message = self.notification_calculator.format_deadline_notification(
                                    training_title=training.title if training else lesson.training_id,
                                    module_number=lesson.module_number,
                                    lesson_title=lesson.lesson_title,
                                    deadline_date=lesson.deadline_date,
                                    students=filtered_students
                                )

                                notification = Notification(
                                    mentor_id=mentor_id,
                                    type='deadlineApproaching',
                                    message=message,
                                    status='pending',
                                    created_at=now_utc
                                )

                                session.add(notification)
                                notifications_created += 1

                                logger.info(
                                    f"Создано уведомление о дедлайне для ментора {mentor_id}, "
                                    f"студентов без ответов: {len(filtered_students)}"
                                )

                    except Exception as e:
                        logger.error(f"Ошибка обработки урока {lesson.lesson_id}: {e}", exc_info=True)
                        continue

                # Коммитим все уведомления
                await session.commit()

                logger.info(
                    f"Проверка дедлайнов завершена. "
                    f"Создано уведомлений: {notifications_created}"
                )

        except Exception as e:
            logger.error(f"Критическая ошибка при проверке дедлайнов: {e}", exc_info=True)

    async def get_approaching_deadlines(
        self,
        session: AsyncSession,
        now_utc: datetime
    ) -> List[Lesson]:
        """
        Получение уроков с приближающимися дедлайнами

        Args:
            session: Сессия БД
            now_utc: Текущее время в UTC

        Returns:
            Список уроков с дедлайнами в пределах warning_hours
        """
        try:
            # Вычисляем порог предупреждения
            warning_threshold = now_utc + timedelta(hours=self.config.deadline_warning_hours)

            query = select(Lesson).where(
                and_(
                    Lesson.deadline_date.isnot(None),
                    Lesson.deadline_date > now_utc,  # Дедлайн еще не прошел
                    Lesson.deadline_date <= warning_threshold,  # Но приближается
                    Lesson.valid_to == datetime(9999, 12, 31, tzinfo=pytz.UTC)
                )
            ).order_by(Lesson.deadline_date)

            result = await session.execute(query)
            return result.scalars().all()

        except Exception as e:
            logger.error(f"Ошибка при получении приближающихся дедлайнов: {e}", exc_info=True)
            return []

    async def get_students_without_answers(
        self,
        session: AsyncSession,
        lesson_getcourse_id: str
    ) -> List[int]:
        """
        Получение студентов без ответов на урок

        Args:
            session: Сессия БД
            lesson_getcourse_id: ID урока из GetCourse

        Returns:
            Список GetCourse ID студентов без ответов
        """
        try:
            # Получаем всех студентов, которые ответили на этот урок
            # (из webhook_events где answer_status = 'new' или 'accepted')
            query = select(WebhookEvent.user_id).where(
                and_(
                    WebhookEvent.answer_lesson_id == lesson_getcourse_id,
                    WebhookEvent.answer_status.in_(['new', 'accepted'])
                )
            ).distinct()

            result = await session.execute(query)
            students_with_answers = set(result.scalars().all())

            # Получаем урок для определения training_id
            lesson_query = select(Lesson).where(
                Lesson.lesson_id == lesson_getcourse_id,
                Lesson.valid_to == datetime(9999, 12, 31, tzinfo=pytz.UTC)
            )
            lesson_result = await session.execute(lesson_query)
            lesson = lesson_result.scalars().first()

            if not lesson:
                return []

            # Получаем training
            training_query = select(Training).where(
                Training.training_id == lesson.training_id,
                Training.valid_to == datetime(9999, 12, 31, tzinfo=pytz.UTC)
            )
            training_result = await session.execute(training_query)
            training = training_result.scalars().first()

            if not training:
                return []

            # Получаем всех студентов этого тренинга через mapping
            mapping_query = select(Mapping).where(
                and_(
                    Mapping.training_id == training.id,
                    Mapping.valid_to == datetime(9999, 12, 31, tzinfo=pytz.UTC)
                )
            )
            mapping_result = await session.execute(mapping_query)
            mappings = mapping_result.scalars().all()

            # Получаем GetCourse ID студентов
            students_without_answers = []
            for mapping in mappings:
                student = await session.get(Student, mapping.student_id)
                if student and student.student_id not in students_with_answers:
                    students_without_answers.append(student.student_id)

            return students_without_answers

        except Exception as e:
            logger.error(f"Ошибка при получении студентов без ответов: {e}", exc_info=True)
            return []

    async def group_students_by_mentor(
        self,
        session: AsyncSession,
        student_getcourse_ids: List[int],
        training_getcourse_id: str
    ) -> Dict[int, List[Dict]]:
        """
        Группировка студентов по наставникам

        Args:
            session: Сессия БД
            student_getcourse_ids: Список GetCourse ID студентов
            training_getcourse_id: GetCourse ID тренинга

        Returns:
            Словарь {mentor_id: [список студентов с данными]}
        """
        try:
            mentor_groups = defaultdict(list)

            # Получаем training
            training_query = select(Training).where(
                Training.training_id == training_getcourse_id,
                Training.valid_to == datetime(9999, 12, 31, tzinfo=pytz.UTC)
            )
            training_result = await session.execute(training_query)
            training = training_result.scalars().first()

            if not training:
                return {}

            # Для каждого студента находим его ментора
            for student_gc_id in student_getcourse_ids:
                # Находим студента
                student_query = select(Student).where(
                    Student.student_id == student_gc_id,
                    Student.valid_to == datetime(9999, 12, 31, tzinfo=pytz.UTC)
                )
                student_result = await session.execute(student_query)
                student = student_result.scalars().first()

                if not student:
                    continue

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
                    continue

                # Добавляем студента в группу его ментора
                mentor_groups[mapping.mentor_id].append({
                    'id': student.id,
                    'student_id': student.student_id,
                    'email': student.user_email,
                    'first_name': student.first_name or '',
                    'last_name': student.last_name or ''
                })

            return dict(mentor_groups)

        except Exception as e:
            logger.error(f"Ошибка при группировке студентов: {e}", exc_info=True)
            return {}
