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
        # Проверка флага включения/выключения напоминаний
        if not self.config.reminder_enabled:
            logger.info("Обработка напоминаний отключена (REMINDER_ENABLED=false)")
            return

        try:
            # 1. Определить дату анализа
            if not analysis_date:
                days_back = self.config.reminder_analysis_days_back
                analysis_date = datetime.now(pytz.UTC) - timedelta(days=days_back)

            # Приводим к началу дня
            analysis_date = analysis_date.replace(hour=0, minute=0, second=0, microsecond=0)

            # убрать\закомментировать логирование после тестирования
            # now_utc = datetime.now(pytz.UTC)
            # now_moscow = now_utc.astimezone(self.moscow_tz)
            # logger.debug(
            #     f"[DEBUG] Обработка напоминаний: дата анализа UTC={analysis_date}, "
            #     f"МСК={analysis_date.astimezone(self.moscow_tz).date()}, "
            #     f"текущее время UTC={now_utc}, МСК={now_moscow}"
            # )

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
                        # Используем UTC-aware datetime.min для консистентности с timezone-aware webhook_date
                        min_utc = datetime.min.replace(tzinfo=pytz.UTC)
                        students.sort(key=lambda s: s.get('webhook_date', min_utc))

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

                        # Получаем ментора для логирования
                        mentor = await session.get(Mentor, mentor_id)
                        if mentor:
                            mentor_name = f"{mentor.first_name or ''} {mentor.last_name or ''}".strip()
                        else:
                            mentor_name = str(mentor_id)
                            # убрать\закомментировать логирование после тестирования
                            # logger.debug(
                            #     f"[DEBUG] Ментор с ID {mentor_id} не найден в БД при логировании"
                            # )

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
                # Проверяем наличие answer_training_id
                if answer.get('answer_training_id') is None:
                    # убрать\закомментировать логирование после тестирования
                    # logger.debug(
                    #     f"[DEBUG] Пропущен ответ студента {answer.get('user_id')}: "
                    #     f"answer_training_id отсутствует"
                    # )
                    continue

                # Преобразуем Integer в строку для поиска тренинга
                try:
                    training_id_str = str(answer['answer_training_id'])
                except (ValueError, TypeError) as e:
                    # убрать\закомментировать логирование после тестирования
                    # logger.debug(
                    #     f"[DEBUG] Ошибка преобразования answer_training_id "
                    #     f"'{answer.get('answer_training_id')}' в строку: {e}"
                    # )
                    continue

                # Находим наставника для этого студента и тренинга
                mentor_id = await self._find_mentor_for_answer(
                    session,
                    answer['user_id'],
                    training_id_str
                )

                if mentor_id:
                    mentor_groups[mentor_id].append(answer)
                    # убрать\закомментировать логирование после тестирования
                    # logger.debug(
                    #     f"[DEBUG] Найден ментор {mentor_id} для студента {answer['user_id']} "
                    #     f"в тренинге {training_id_str}"
                    # )
                else:
                    logger.warning(
                        f"Не найден наставник для студента {answer['user_id']} "
                        f"в тренинге {training_id_str}"
                    )

            # убрать\закомментировать логирование после тестирования
            # logger.debug(
            #     f"[DEBUG] group_answers_by_mentor: обработано ответов {len(answers)}, "
            #     f"найдено менторов {len(mentor_groups)}"
            # )

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
            training_getcourse_id: GetCourse ID тренинга (строка)

        Returns:
            ID ментора (из таблицы mentors) или None
        """
        try:
            # Текущее время для проверки актуальности записей
            now_utc = datetime.now(pytz.UTC)

            # убрать\закомментировать логирование после тестирования
            # logger.debug(
            #     f"[DEBUG] _find_mentor_for_answer: student_getcourse_id={student_getcourse_id}, "
            #     f"training_getcourse_id={training_getcourse_id}, now_utc={now_utc}"
            # )

            # Находим студента по GetCourse ID с проверкой актуальности
            student_query = select(Student).where(
                and_(
                    Student.student_id == student_getcourse_id,
                    Student.valid_from <= now_utc,
                    Student.valid_to >= now_utc
                )
            )
            student_result = await session.execute(student_query)
            student = student_result.scalars().first()

            if not student:
                # убрать\закомментировать логирование после тестирования
                # logger.debug(
                #     f"[DEBUG] Студент с GetCourse ID {student_getcourse_id} не найден или неактуален"
                # )
                return None

            # убрать\закомментировать логирование после тестирования
            # logger.debug(
            #     f"[DEBUG] Найден студент: id={student.id}, student_id={student.student_id}, "
            #     f"valid_from={student.valid_from}, valid_to={student.valid_to}"
            # )

            # Находим тренинг по GetCourse ID с проверкой актуальности
            training_query = select(Training).where(
                and_(
                    Training.training_id == training_getcourse_id,
                    Training.valid_from <= now_utc,
                    Training.valid_to >= now_utc
                )
            )
            training_result = await session.execute(training_query)
            training = training_result.scalars().first()

            if not training:
                # убрать\закомментировать логирование после тестирования
                # logger.debug(
                #     f"[DEBUG] Тренинг с GetCourse ID {training_getcourse_id} не найден или неактуален"
                # )
                return None

            # убрать\закомментировать логирование после тестирования
            # logger.debug(
            #     f"[DEBUG] Найден тренинг: id={training.id}, training_id={training.training_id}, "
            #     f"valid_from={training.valid_from}, valid_to={training.valid_to}"
            # )

            # Находим mapping по GetCourse ID с проверкой актуальности
            # ВАЖНО: mapping.student_id и mapping.training_id хранят GetCourse ID
            # (как в webhook_processor и deadline_checker)
            # Приводим training_getcourse_id к int для сравнения
            try:
                training_gc_id_int = int(training_getcourse_id)
            except (ValueError, TypeError):
                logger.error(
                    f"Не удалось преобразовать training_getcourse_id '{training_getcourse_id}' в int"
                )
                return None

            mapping_query = select(Mapping).where(
                and_(
                    Mapping.student_id == student.student_id,  # GetCourse ID студента
                    Mapping.training_id == training_gc_id_int,  # GetCourse ID тренинга
                    Mapping.valid_from <= now_utc,
                    Mapping.valid_to >= now_utc
                )
            )
            mapping_result = await session.execute(mapping_query)
            mapping = mapping_result.scalars().first()

            if not mapping:
                # убрать\закомментировать логирование после тестирования
                # logger.debug(
                #     f"[DEBUG] Mapping не найден для student.student_id={student.student_id}, "
                #     f"training.training_id={training.training_id}"
                # )
                return None

            # убрать\закомментировать логирование после тестирования
            # logger.debug(
            #     f"[DEBUG] Найден mapping: id={mapping.id}, student_id={mapping.student_id}, "
            #     f"training_id={mapping.training_id}, mentor_id={mapping.mentor_id}, "
            #     f"valid_from={mapping.valid_from}, valid_to={mapping.valid_to}"
            # )

            # Находим ментора по его GetCourse mentor_id,
            # чтобы вернуть внутренний mentors.id (как в webhook_processor и deadline_checker)
            mentor_query = select(Mentor).where(
                and_(
                    Mentor.mentor_id == mapping.mentor_id,  # mapping.mentor_id - это GetCourse ID
                    Mentor.valid_from <= now_utc,
                    Mentor.valid_to >= now_utc,
                )
            )
            mentor_result = await session.execute(mentor_query)
            mentor = mentor_result.scalars().first()

            if not mentor:
                # убрать\закомментировать логирование после тестирования
                # logger.debug(
                #     f"[DEBUG] Ментор с GetCourse ID {mapping.mentor_id} не найден или неактуален"
                # )
                return None

            # Возвращаем внутренний ID ментора (mentors.id), который нужен для notifications.mentor_id
            return mentor.id

        except Exception as e:
            logger.error(f"Ошибка при поиске ментора: {e}", exc_info=True)
            return None