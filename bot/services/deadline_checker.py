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
    WebhookEvent, Notification, Mentor
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
                now_moscow = now_utc.astimezone(self.moscow_tz)

                # убрать\закомментировать логирование после тестирования
                # logger.info(
                #     f"[DEBUG] Текущее время UTC: {now_utc}, МСК: {now_moscow}, "
                #     f"DEADLINE_WARNING_HOURS: {self.config.deadline_warning_hours}"
                # )

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
                    # убрать\закомментировать логирование после тестирования
                    # lesson_deadline_moscow = lesson.deadline_date.astimezone(self.moscow_tz) if lesson.deadline_date else None
                    # logger.info(
                    #     f"[DEBUG] Обработка урока: lesson_id={lesson.lesson_id}, "
                    #     f"training_id={lesson.training_id}, "
                    #     f"deadline UTC={lesson.deadline_date}, "
                    #     f"deadline МСК={lesson_deadline_moscow}"
                    # )
                    try:
                        # Получить студентов без ответов
                        students_without_answers = await self.get_students_without_answers(
                            session,
                            lesson.lesson_id
                        )

                        # убрать\закомментировать логирование после тестирования
                        # logger.info(
                        #     f"[DEBUG] Урок {lesson.lesson_id}: найдено студентов без ответов: {len(students_without_answers)}"
                        # )

                        if not students_without_answers:
                            # убрать\закомментировать логирование после тестирования
                            # logger.info(f"[DEBUG] Урок {lesson.lesson_id}: нет студентов без ответов, пропускаем")
                            continue

                        # Сгруппировать студентов по наставникам
                        mentor_groups = await self.group_students_by_mentor(
                            session,
                            students_without_answers,
                            lesson.training_id
                        )

                        # убрать\закомментировать логирование после тестирования
                        # logger.info(
                        #     f"[DEBUG] Урок {lesson.lesson_id}: студентов сгруппировано по {len(mentor_groups)} менторам"
                        # )

                        # Создать уведомления для каждого ментора
                        for mentor_id, students in mentor_groups.items():
                            # убрать\закомментировать логирование после тестирования
                            # logger.info(
                            #     f"[DEBUG] Урок {lesson.lesson_id}: ментор {mentor_id}, "
                            #     f"студентов в группе: {len(students)}"
                            # )
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
                                message = self.notification_calculator.format_deadline_notification(
                                    module_title=lesson.module_title,
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

            # убрать\закомментировать логирование после тестирования
            # warning_threshold_moscow = warning_threshold.astimezone(self.moscow_tz)
            # now_moscow = now_utc.astimezone(self.moscow_tz)
            # logger.info(
            #     f"[DEBUG] get_approaching_deadlines: now_utc={now_utc} (МСК: {now_moscow}), "
            #     f"warning_threshold={warning_threshold} (МСК: {warning_threshold_moscow}), "
            #     f"warning_hours={self.config.deadline_warning_hours}"
            # )

            # убрать\закомментировать логирование после тестирования
            # Сначала получим уроки с дедлайнами с теми же условиями актуальности, что и в основном запросе
            # ВАЖНО: используем интервальную проверку valid_from/valid_to, а не сравнение с '9999-12-31',
            # т.к. TIMESTAMPTZ в БД хранится с часовым поясом и прямое сравнение с UTC-датой может не совпасть.
            # all_lessons_query = select(Lesson).where(
            #     and_(
            #         Lesson.deadline_date.isnot(None),
            #         Lesson.deadline_date > now_utc,
            #         Lesson.deadline_date <= warning_threshold,
            #         Lesson.valid_from <= now_utc,
            #         Lesson.valid_to >= now_utc
            #     )
            # ).order_by(Lesson.deadline_date)
            # all_lessons_result = await session.execute(all_lessons_query)
            # all_lessons = all_lessons_result.scalars().all()
            # logger.info(f"[DEBUG] Всего уроков с дедлайнами в БД: {len(all_lessons)}")
            # for lesson in all_lessons:
            #     lesson_deadline_moscow = lesson.deadline_date.astimezone(self.moscow_tz) if lesson.deadline_date else None
            #     deadline_passed = lesson.deadline_date <= now_utc if lesson.deadline_date else None
            #     deadline_in_range = (lesson.deadline_date > now_utc and lesson.deadline_date <= warning_threshold) if lesson.deadline_date else None
            #     logger.info(
            #         f"[DEBUG]   Урок {lesson.lesson_id}: deadline UTC={lesson.deadline_date}, "
            #         f"МСК={lesson_deadline_moscow}, прошел={deadline_passed}, "
            #         f"в диапазоне={deadline_in_range}"
            #     )

            query = select(Lesson).where(
                and_(
                    Lesson.deadline_date.isnot(None),
                    Lesson.deadline_date > now_utc,           # Дедлайн еще не прошел
                    Lesson.deadline_date <= warning_threshold,  # Но приближается
                    # ВАЖНО: актуальность записи урока по периодам valid_from/valid_to
                    Lesson.valid_from <= now_utc,
                    Lesson.valid_to >= now_utc
                )
            ).order_by(Lesson.deadline_date)

            result = await session.execute(query)
            lessons = result.scalars().all()

            # убрать\закомментировать логирование после тестирования
            # logger.info(f"[DEBUG] get_approaching_deadlines: найдено уроков после фильтрации: {len(lessons)}")
            # for lesson in lessons:
            #     lesson_deadline_moscow = lesson.deadline_date.astimezone(self.moscow_tz) if lesson.deadline_date else None
            #     logger.info(
            #         f"[DEBUG]   - Урок {lesson.lesson_id}: deadline UTC={lesson.deadline_date}, "
            #         f"МСК={lesson_deadline_moscow}, training_id={lesson.training_id}"
            #     )

            return lessons

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
            # Текущее время для проверки актуальности записей
            now_utc = datetime.now(pytz.UTC)

            # Получаем всех студентов, которые ответили на этот урок
            # (из webhook_events где answer_status = 'new' или 'accepted')
            # ВАЖНО: answer_lesson_id в БД имеет тип Integer, поэтому приводим строку к int
            try:
                lesson_id_int = int(lesson_getcourse_id)
            except (ValueError, TypeError):
                logger.error(
                    f"Не удалось преобразовать lesson_getcourse_id '{lesson_getcourse_id}' в int"
                )
                return []

            query = select(WebhookEvent.user_id).where(
                and_(
                    WebhookEvent.answer_lesson_id == lesson_id_int,
                    WebhookEvent.answer_status.in_(['new', 'accepted'])
                )
            ).distinct()

            result = await session.execute(query)
            students_with_answers = set(result.scalars().all())

            # убрать\закомментировать логирование после тестирования
            # logger.info(
            #     f"[DEBUG] get_students_without_answers для урока {lesson_getcourse_id}: "
            #     f"студентов с ответами: {len(students_with_answers)}"
            # )

            # Получаем урок для определения training_id
            lesson_query = select(Lesson).where(
                Lesson.lesson_id == lesson_getcourse_id,
                # ВАЖНО: проверяем актуальность записи по интервалу valid_from/valid_to
                Lesson.valid_from <= now_utc,
                Lesson.valid_to >= now_utc
            )
            lesson_result = await session.execute(lesson_query)
            lesson = lesson_result.scalars().first()

            if not lesson:
                # убрать\закомментировать логирование после тестирования
                # logger.warning(f"[DEBUG] Урок {lesson_getcourse_id} не найден в БД")
                return []

            # Получаем всех студентов этого тренинга через mapping.
            # ВАЖНО: в mapping.training_id хранится GetCourse ID тренинга (Integer),
            # а в Lesson.training_id — строковый GetCourse ID, поэтому приводим к int.
            try:
                training_gc_id_int = int(lesson.training_id)
            except (ValueError, TypeError):
                logger.error(
                    f"Не удалось преобразовать lesson.training_id '{lesson.training_id}' в int "
                    f"для урока {lesson_getcourse_id}"
                )
                return []

            mapping_query = select(Mapping).where(
                and_(
                    Mapping.training_id == training_gc_id_int,
                    Mapping.valid_from <= now_utc,
                    Mapping.valid_to >= now_utc
                )
            )
            mapping_result = await session.execute(mapping_query)
            mappings = mapping_result.scalars().all()

            # убрать\закомментировать логирование после тестирования
            # logger.info(
            #     f"[DEBUG] get_students_without_answers для урока {lesson_getcourse_id}: "
            #     f"всего mappings для тренинга {training_gc_id_int}: {len(mappings)}"
            # )

            # Получаем GetCourse ID студентов
            # ВАЖНО: mapping.student_id - это Student.student_id (GetCourse ID), а не Student.id
            # Приводим к int, т.к. в БД Mapping.student_id - BigInteger, а Student.student_id - Integer
            students_without_answers = []
            for mapping in mappings:
                try:
                    mapping_student_id_int = int(mapping.student_id)
                except (ValueError, TypeError):
                    logger.warning(
                        f"Не удалось преобразовать mapping.student_id '{mapping.student_id}' в int"
                    )
                    continue

                # Ищем студента по GetCourse ID, а не по внутреннему id
                student_query = select(Student).where(
                    Student.student_id == mapping_student_id_int,
                    Student.valid_from <= now_utc,
                    Student.valid_to >= now_utc
                )
                student_result = await session.execute(student_query)
                student = student_result.scalars().first()

                if student and student.student_id not in students_with_answers:
                    students_without_answers.append(student.student_id)

            # убрать\закомментировать логирование после тестирования
            # logger.info(
            #     f"[DEBUG] get_students_without_answers для урока {lesson_getcourse_id}: "
            #     f"студентов без ответов: {len(students_without_answers)} "
            #     f"(из {len(mappings)} mappings в тренинге)"
            # )

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
            # Текущее время для проверки актуальности записей
            now_utc = datetime.now(pytz.UTC)

            mentor_groups = defaultdict(list)

            # Получаем training по GetCourse ID (строка)
            training_query = select(Training).where(
                Training.training_id == str(training_getcourse_id),
                Training.valid_from <= now_utc,
                Training.valid_to >= now_utc
            )
            training_result = await session.execute(training_query)
            training = training_result.scalars().first()

            if not training:
                return {}

            # Приводим GetCourse ID тренинга к int для работы с mapping.training_id
            try:
                training_gc_id_int = int(training_getcourse_id)
            except (ValueError, TypeError):
                logger.error(
                    f"Не удалось преобразовать training_getcourse_id '{training_getcourse_id}' в int "
                    f"в group_students_by_mentor"
                )
                return {}

            # Для каждого студента находим его ментора
            for student_gc_id in student_getcourse_ids:
                # Приводим к int для надежности (Mapping.student_id - BigInteger)
                try:
                    student_gc_id_int = int(student_gc_id)
                except (ValueError, TypeError):
                    logger.warning(
                        f"Не удалось преобразовать student_gc_id '{student_gc_id}' в int "
                        f"в group_students_by_mentor"
                    )
                    continue

                # Находим студента по его GetCourse ID
                student_query = select(Student).where(
                    Student.student_id == student_gc_id_int,
                    Student.valid_from <= now_utc,
                    Student.valid_to >= now_utc
                )
                student_result = await session.execute(student_query)
                student = student_result.scalars().first()

                if not student:
                    continue

                # Находим mapping.
                # В mapping.student_id хранится GetCourse ID студента,
                # в mapping.training_id — GetCourse ID тренинга.
                mapping_query = select(Mapping).where(
                    and_(
                        Mapping.student_id == student_gc_id_int,
                        Mapping.training_id == training_gc_id_int,
                        Mapping.valid_from <= now_utc,
                        Mapping.valid_to >= now_utc
                    )
                )
                mapping_result = await session.execute(mapping_query)
                mapping = mapping_result.scalars().first()

                if not mapping:
                    continue

                # Находим ментора по его GetCourse mentor_id,
                # чтобы дальше использовать внутренний mentors.id в notifications
                mentor_query = select(Mentor).where(
                    and_(
                        Mentor.mentor_id == mapping.mentor_id,
                        Mentor.valid_from <= now_utc,
                        Mentor.valid_to >= now_utc,
                    )
                )
                mentor_result = await session.execute(mentor_query)
                mentor = mentor_result.scalars().first()

                if not mentor:
                    continue

                # Добавляем студента в группу его ментора (ключ — mentors.id)
                mentor_groups[mentor.id].append({
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
