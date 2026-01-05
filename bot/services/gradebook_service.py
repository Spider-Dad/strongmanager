from __future__ import annotations

import logging
from collections import defaultdict, Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Iterable, Set

import pytz
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.database import (
    Mentor,
    Student,
    Mapping,
    Training,
    Lesson,
    WebhookEvent,
)

logger = logging.getLogger(__name__)


# ВРЕМЕННЫЙ КОСТЫЛЬ: приводим все datetime к naive для исключения смешения aware/naive
def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    try:
        return dt.replace(tzinfo=None) if getattr(dt, "tzinfo", None) else dt
    except Exception:
        # На всякий случай не ломаемся на неожиданных типах
        return dt

# Статусы табеля
STATUS_ON_TIME = "on_time"  # сдал вовремя
STATUS_LATE = "late"  # сдал с опозданием
STATUS_NO_BEFORE_DEADLINE = "no_before_deadline"  # не сдал, дедлайн не прошёл
STATUS_NO_AFTER_DEADLINE = "no_after_deadline"  # не сдал, дедлайн прошёл
STATUS_OPTIONAL = "optional"  # необязательный урок без дедлайна

NOT_ON_TIME_SET = {STATUS_LATE, STATUS_NO_BEFORE_DEADLINE, STATUS_NO_AFTER_DEADLINE}

# Упрощенные статусы для отображения
STATUS_HAS_ANSWER = "has_answer"  # Есть ответ (объединяет STATUS_ON_TIME + STATUS_LATE)
STATUS_NO_ANSWER = "no_answer"    # Нет ответа (объединяет STATUS_NO_BEFORE_DEADLINE + STATUS_NO_AFTER_DEADLINE)


def simplify_status(status: str) -> Optional[str]:
    """
    Преобразует детальный статус в упрощенный формат для отображения.

    Args:
        status: Один из детальных статусов (STATUS_*)

    Returns:
        STATUS_HAS_ANSWER, STATUS_NO_ANSWER или None (для STATUS_OPTIONAL)
    """
    if status in {STATUS_ON_TIME, STATUS_LATE}:
        return STATUS_HAS_ANSWER
    elif status in {STATUS_NO_BEFORE_DEADLINE, STATUS_NO_AFTER_DEADLINE}:
        return STATUS_NO_ANSWER
    else:
        # STATUS_OPTIONAL и другие - не показываем в статистике
        return None


@dataclass
class LessonStatus:
    student_id: int
    lesson_id: int
    status: str
    deadline: Optional[datetime]
    answer_date: Optional[datetime]


def categorize_status(deadline: Optional[datetime], earliest_answer_date: Optional[datetime], now: Optional[datetime] = None) -> str:
    """
    Возвращает один из статусов STATUS_* по дедлайну и дате ответа.

    Правила:
    - Нет ответа: now < deadline → no_before_deadline; иначе → no_after_deadline
    - Есть ответ: answer_date ≤ deadline → on_time; иначе → late
    - Если дедлайн отсутствует: нет ответа → optional; есть ответ → on_time

    ВАЖНО: Все сравнения выполняются в UTC для корректной работы с timezone-aware datetime из БД.
    """
    # Используем UTC для корректного сравнения с данными из БД (TIMESTAMPTZ)
    if now is None:
        current_time = datetime.now(pytz.UTC)
    else:
        # Если передан naive datetime, преобразуем в UTC
        if now.tzinfo is None:
            current_time = pytz.UTC.localize(now)
        else:
            current_time = now.astimezone(pytz.UTC)

    # Нормализуем deadline в UTC
    if deadline:
        if deadline.tzinfo is None:
            deadline_utc = pytz.UTC.localize(deadline)
        else:
            deadline_utc = deadline.astimezone(pytz.UTC)
    else:
        deadline_utc = None

    # Нормализуем earliest_answer_date в UTC
    if earliest_answer_date:
        if earliest_answer_date.tzinfo is None:
            answer_date_utc = pytz.UTC.localize(earliest_answer_date)
        else:
            answer_date_utc = earliest_answer_date.astimezone(pytz.UTC)
    else:
        answer_date_utc = None

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] categorize_status: current_time (UTC)={current_time}, deadline (UTC)={deadline_utc}, "
    #              f"answer_date (UTC)={answer_date_utc}")

    if deadline_utc is None:
        # Для уроков без дедлайна
        if answer_date_utc is None:
            # убрать\закомментировать логирование после тестирования
            # logger.debug(f"[DEBUG] categorize_status: STATUS_OPTIONAL (нет дедлайна, нет ответа)")
            return STATUS_OPTIONAL  # новый статус для необязательных уроков
        else:
            # убрать\закомментировать логирование после тестирования
            # logger.debug(f"[DEBUG] categorize_status: STATUS_ON_TIME (нет дедлайна, есть ответ)")
            return STATUS_ON_TIME  # ответ дан, считаем вовремя

    if answer_date_utc is None:
        # Нет ответа: сравниваем текущее время с дедлайном
        if current_time < deadline_utc:
            # убрать\закомментировать логирование после тестирования
            # logger.debug(f"[DEBUG] categorize_status: STATUS_NO_BEFORE_DEADLINE (нет ответа, дедлайн не прошел: {current_time} < {deadline_utc})")
            return STATUS_NO_BEFORE_DEADLINE
        else:
            # убрать\закомментировать логирование после тестирования
            # logger.debug(f"[DEBUG] categorize_status: STATUS_NO_AFTER_DEADLINE (нет ответа, дедлайн прошел: {current_time} >= {deadline_utc})")
            return STATUS_NO_AFTER_DEADLINE

    # Есть ответ: сравниваем дату ответа с дедлайном
    if answer_date_utc <= deadline_utc:
        # убрать\закомментировать логирование после тестирования
        # logger.debug(f"[DEBUG] categorize_status: STATUS_ON_TIME (есть ответ, вовремя: {answer_date_utc} <= {deadline_utc})")
        return STATUS_ON_TIME
    else:
        # убрать\закомментировать логирование после тестирования
        # logger.debug(f"[DEBUG] categorize_status: STATUS_LATE (есть ответ, с опозданием: {answer_date_utc} > {deadline_utc})")
        return STATUS_LATE


async def _fetch_students_for_mentor(session: AsyncSession, mentor_id: int) -> Dict[int, Student]:
    """
    Получает студентов для наставника.

    Args:
        session: Сессия БД
        mentor_id: Внутренний ID наставника (Mentor.id)

    Returns:
        Словарь {внутренний Student.id: Student}
    """
    # Текущее время для проверки актуальности записей
    now_utc = datetime.now(pytz.UTC)

    # Находим ментора по внутреннему ID, чтобы получить GetCourse ID
    mentor_query = select(Mentor).where(
        and_(
            Mentor.id == mentor_id,
            Mentor.valid_from <= now_utc,
            Mentor.valid_to >= now_utc
        )
    )
    mentor_result = await session.execute(mentor_query)
    mentor = mentor_result.scalars().first()

    if not mentor:
        # убрать\закомментировать логирование после тестирования
        # logger.debug(f"[DEBUG] _fetch_students_for_mentor: ментор с внутренним ID {mentor_id} не найден или неактуален")
        return {}

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] _fetch_students_for_mentor: найден ментор id={mentor.id}, mentor_id (GetCourse)={mentor.mentor_id}")

    # ВАЖНО: Mapping.mentor_id хранит GetCourse ID ментора (Mentor.mentor_id), а не внутренний Mentor.id
    # Mapping.student_id хранит GetCourse ID студента (Student.student_id), а не внутренний Student.id
    mapping_rows = await session.execute(
        select(Mapping.student_id).where(
            and_(
                Mapping.mentor_id == mentor.mentor_id,  # GetCourse ID ментора
                Mapping.valid_from <= now_utc,
                Mapping.valid_to >= now_utc
            )
        )
    )
    student_getcourse_ids = [row[0] for row in mapping_rows.fetchall()]

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] _fetch_students_for_mentor: найдено mappings с GetCourse ID студентов: {student_getcourse_ids}")

    if not student_getcourse_ids:
        return {}

    # Ищем студентов по GetCourse ID (Student.student_id), а не по внутреннему Student.id
    students_res = await session.execute(
        select(Student).where(
            and_(
                Student.student_id.in_(student_getcourse_ids),
                Student.valid_from <= now_utc,
                Student.valid_to >= now_utc
            )
        )
    )
    students: List[Student] = students_res.scalars().all()

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] _fetch_students_for_mentor: найдено студентов: {len(students)}")
    # for s in students:
    #     logger.debug(f"[DEBUG]   - Студент: внутренний id={s.id}, student_id (GetCourse)={s.student_id}, email={s.user_email}")

    return {s.id: s for s in students}


async def _fetch_trainings_for_mentor(session: AsyncSession, mentor_id: int) -> Set[str]:
    """
    Получает GetCourse ID тренингов для наставника.

    Args:
        session: Сессия БД
        mentor_id: Внутренний ID наставника (Mentor.id)

    Returns:
        Множество GetCourse ID тренингов (Training.training_id как String)
    """
    # Текущее время для проверки актуальности записей
    now_utc = datetime.now(pytz.UTC)

    # Находим ментора по внутреннему ID, чтобы получить GetCourse ID
    mentor_query = select(Mentor).where(
        and_(
            Mentor.id == mentor_id,
            Mentor.valid_from <= now_utc,
            Mentor.valid_to >= now_utc
        )
    )
    mentor_result = await session.execute(mentor_query)
    mentor = mentor_result.scalars().first()

    if not mentor:
        # убрать\закомментировать логирование после тестирования
        # logger.debug(f"[DEBUG] _fetch_trainings_for_mentor: ментор с внутренним ID {mentor_id} не найден или неактуален")
        return set()

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] _fetch_trainings_for_mentor: найден ментор id={mentor.id}, mentor_id (GetCourse)={mentor.mentor_id}")

    # ВАЖНО: Mapping.mentor_id хранит GetCourse ID ментора (Mentor.mentor_id)
    # Mapping.training_id хранит GetCourse ID тренинга (BigInteger, но Training.training_id - String)
    mapping_rows = await session.execute(
        select(Mapping.training_id).where(
            and_(
                Mapping.mentor_id == mentor.mentor_id,  # GetCourse ID ментора
                Mapping.valid_from <= now_utc,
                Mapping.valid_to >= now_utc
            )
        )
    )
    training_getcourse_ids = {str(row[0]) for row in mapping_rows.fetchall()}  # Преобразуем в String для Training.training_id

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] _fetch_trainings_for_mentor: найдено GetCourse ID тренингов: {training_getcourse_ids}")

    return training_getcourse_ids


async def _fetch_lessons_for_trainings(session: AsyncSession, training_ids: Iterable[str]) -> List[Lesson]:
    """
    Получает уроки для тренингов по их GetCourse ID.

    Args:
        session: Сессия БД
        training_ids: Итерируемый объект GetCourse ID тренингов (Training.training_id как String)

    Returns:
        Список уроков
    """
    if not training_ids:
        return []

    # Текущее время для проверки актуальности записей
    now_utc = datetime.now(pytz.UTC)

    training_ids_list = list(set(training_ids))

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] _fetch_lessons_for_trainings: поиск уроков для тренингов с GetCourse ID: {training_ids_list}")

    # ВАЖНО: Lesson.training_id имеет тип String и хранит GetCourse ID тренинга (Training.training_id)
    result = await session.execute(
        select(Lesson).where(
            and_(
                Lesson.training_id.in_(training_ids_list),
                Lesson.valid_from <= now_utc,
                Lesson.valid_to >= now_utc
            )
        )
    )
    lessons = result.scalars().all()

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] _fetch_lessons_for_trainings: найдено уроков: {len(lessons)}")

    return lessons


def get_lesson_state(lesson: Lesson, now: Optional[datetime] = None) -> str:
    """
    Возвращает состояние урока: not_started | active | completed.

    ВАЖНО: Все сравнения выполняются в UTC для корректной работы с timezone-aware datetime из БД.
    """
    # Используем UTC для корректного сравнения с данными из БД (TIMESTAMPTZ)
    if now is None:
        current_time = datetime.now(pytz.UTC)
    else:
        # Если передан naive datetime, преобразуем в UTC
        if now.tzinfo is None:
            current_time = pytz.UTC.localize(now)
        else:
            current_time = now.astimezone(pytz.UTC)

    # Даты из БД уже в UTC (TIMESTAMPTZ), но на всякий случай нормализуем
    opening_date = lesson.opening_date
    if opening_date and opening_date.tzinfo is None:
        opening_date = pytz.UTC.localize(opening_date)
    elif opening_date:
        opening_date = opening_date.astimezone(pytz.UTC)

    deadline_date = lesson.deadline_date
    if deadline_date and deadline_date.tzinfo is None:
        deadline_date = pytz.UTC.localize(deadline_date)
    elif deadline_date:
        deadline_date = deadline_date.astimezone(pytz.UTC)

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] get_lesson_state: lesson_id={lesson.lesson_id}, current_time (UTC)={current_time}, "
    #              f"opening_date (UTC)={opening_date}, deadline_date (UTC)={deadline_date}")

    if opening_date and opening_date > current_time:
        # убрать\закомментировать логирование после тестирования
        # logger.debug(f"[DEBUG] get_lesson_state: урок {lesson.lesson_id} - not_started (opening_date > current_time)")
        return "not_started"

    # Для уроков без дедлайна - всегда active после открытия
    if not deadline_date:
        if opening_date and opening_date <= current_time:
            # убрать\закомментировать логирование после тестирования
            # logger.debug(f"[DEBUG] get_lesson_state: урок {lesson.lesson_id} - active (без дедлайна, открыт)")
            return "active"
        # убрать\закомментировать логирование после тестирования
        # logger.debug(f"[DEBUG] get_lesson_state: урок {lesson.lesson_id} - not_started (без дедлайна, не открыт)")
        return "not_started"

    # Для уроков с дедлайном - стандартная логика
    if deadline_date <= current_time:
        # убрать\закомментировать логирование после тестирования
        # logger.debug(f"[DEBUG] get_lesson_state: урок {lesson.lesson_id} - completed (deadline_date <= current_time: {deadline_date} <= {current_time})")
        return "completed"

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] get_lesson_state: урок {lesson.lesson_id} - active (deadline_date > current_time: {deadline_date} > {current_time})")
    return "active"


def get_training_state(lessons: List[Lesson], training: Training = None, now: Optional[datetime] = None) -> str:
    """Состояние тренинга по датам тренинга или урокам."""
    if not lessons:
        return "not_started"

    current_time = _naive(now) or _naive(datetime.now())

    # Используем даты тренинга для определения состояния
    if training and training.start_date and training.end_date:
        start_date = _naive(training.start_date)
        end_date = _naive(training.end_date)
        if current_time < start_date:
            return "not_started"
        elif current_time >= end_date:
            return "completed"
        else:
            return "active"

    # Fallback: если нет дат тренинга, используем даты уроков
    opening_dates = [_naive(l.opening_date) for l in lessons if l.opening_date]
    deadline_dates = [_naive(l.deadline_date) for l in lessons if l.deadline_date]

    if opening_dates:
        earliest_opening = min(opening_dates)
        if current_time < earliest_opening:
            return "not_started"

    if deadline_dates:
        latest_deadline = max(deadline_dates)
        if current_time >= latest_deadline:
            return "completed"

    return "active"


def get_status_emoji(state: str) -> str:
    """Возвращает эмодзи для статуса урока/тренинга."""
    if state == "active":
        return "🟡"
    elif state == "completed":
        return "🟢"
    elif state == "not_started":
        return "🔴"
    return ""








async def _fetch_logs_earliest_by_student_lesson(
    session: AsyncSession,
    student_id_to_email: Dict[int, str],
    lesson_getcourse_ids: Iterable[int],
) -> Dict[Tuple[int, int], datetime]:
    """
    Возвращает (student_id, lesson_getcourse_id) -> earliest_answer_date по email студента и GetCourse ID урока.

    ВАЖНО: Использует таблицу WebhookEvent (не DEPRECATED Log).
    ВАЖНО: lesson_getcourse_ids - это GetCourse ID уроков (Integer), а не внутренние Lesson.id.
    ВАЖНО: Возвращает ключи с GetCourse ID урока для сопоставления с Lesson.lesson_id.

    Args:
        session: Сессия БД
        student_id_to_email: Словарь {внутренний Student.id: email}
        lesson_getcourse_ids: GetCourse ID уроков (Integer из Lesson.lesson_id)

    Returns:
        Словарь {(внутренний Student.id, GetCourse ID урока): earliest_answer_date}
    """
    emails = list({e for e in student_id_to_email.values() if e})
    lesson_ids_list = [int(lid) for lid in lesson_getcourse_ids]  # Преобразуем в int для WebhookEvent.answer_lesson_id

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] _fetch_logs_earliest_by_student_lesson: emails={emails}, lesson_getcourse_ids={lesson_ids_list}")

    if not emails or not lesson_ids_list:
        # убрать\закомментировать логирование после тестирования
        # logger.debug(f"[DEBUG] _fetch_logs_earliest_by_student_lesson: пустые emails или lesson_ids, возвращаем пустой словарь")
        return {}

    # ВАЖНО: Используем WebhookEvent вместо DEPRECATED Log
    # WebhookEvent.answer_lesson_id хранит GetCourse ID урока (Integer)
    # Фильтруем по статусам 'new' и 'accepted' (как в deadline_checker и reminder_service)
    res = await session.execute(
        select(WebhookEvent.user_email, WebhookEvent.answer_lesson_id, func.min(WebhookEvent.event_date))
        .where(
            and_(
                WebhookEvent.user_email.in_(emails),
                WebhookEvent.answer_lesson_id.in_(lesson_ids_list),
                WebhookEvent.answer_status.in_(['new', 'accepted'])  # Только актуальные ответы
            )
        )
        .group_by(WebhookEvent.user_email, WebhookEvent.answer_lesson_id)
    )

    email_to_student = {email: sid for sid, email in student_id_to_email.items() if email}

    earliest: Dict[Tuple[int, int], datetime] = {}
    for user_email, lesson_getcourse_id, min_date in res.fetchall():
        student_id = email_to_student.get(user_email)
        if student_id is not None and min_date is not None:
            # Ключ: (внутренний Student.id, GetCourse ID урока)
            earliest[(student_id, lesson_getcourse_id)] = min_date
            # убрать\закомментировать логирование после тестирования
            # logger.debug(f"[DEBUG] _fetch_logs_earliest_by_student_lesson: найдено - student_id={student_id}, lesson_getcourse_id={lesson_getcourse_id}, date={min_date}")

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] _fetch_logs_earliest_by_student_lesson: всего найдено записей: {len(earliest)}")

    return earliest


def _resolve_deadline(lesson: Lesson) -> Optional[datetime]:
    """Возвращает дедлайн урока"""
    return lesson.deadline_date


def _safe_int_lesson_id(lesson_id: str) -> Optional[int]:
    """
    Безопасно преобразует lesson_id (String) в int.

    Args:
        lesson_id: Строковый ID урока из БД

    Returns:
        Integer ID урока или None, если преобразование невозможно
    """
    try:
        return int(lesson_id)
    except (ValueError, TypeError):
        logger.error(f"Не удалось преобразовать lesson_id '{lesson_id}' в int")
        return None


async def build_mentor_overview(
    session: AsyncSession,
    mentor_id: int,
    training_id: Optional[int] = None,
    lesson_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    include_not_started: bool = False,
) -> Dict[str, object]:
    """
    Возвращает агрегированную сводку для наставника по его студентам.

    Args:
        session: Сессия БД
        mentor_id: Внутренний ID наставника (Mentor.id)
        training_id: Внутренний ID тренинга (Training.id) - опционально
        lesson_id: Внутренний ID урока (Lesson.id) - опционально
        status_filter: Фильтр по статусу (один из STATUS_*) - опционально
        include_not_started: Включать ли уроки в состоянии not_started

    Returns:
        Словарь с агрегированными данными
    """
    # Текущее время для проверки актуальности записей
    now_utc = datetime.now(pytz.UTC)

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] build_mentor_overview: mentor_id (внутренний)={mentor_id}, training_id={training_id}, lesson_id={lesson_id}")

    students = await _fetch_students_for_mentor(session, mentor_id)
    if not students:
        # убрать\закомментировать логирование после тестирования
        # logger.debug(f"[DEBUG] build_mentor_overview: нет студентов для ментора {mentor_id}")
        return {"total_students": 0, "counts": {}, "by_lesson": {}, "by_student": {}, "items": []}

    # Получаем все тренинги наставника (training_id игнорируется для совместимости)
    mentor_training_getcourse_ids = await _fetch_trainings_for_mentor(session, mentor_id)
    training_ids = mentor_training_getcourse_ids

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] build_mentor_overview: GetCourse ID тренингов для фильтрации: {training_ids}")

    lessons = await _fetch_lessons_for_trainings(session, training_ids)

    # Если передан lesson_id (внутренний ID), фильтруем уроки
    if lesson_id is not None:
        lessons = [l for l in lessons if l.id == lesson_id]
        # убрать\закомментировать логирование после тестирования
        # logger.debug(f"[DEBUG] build_mentor_overview: после фильтрации по lesson_id={lesson_id} осталось уроков: {len(lessons)}")

    if not lessons:
        # убрать\закомментировать логирование после тестирования
        # logger.debug(f"[DEBUG] build_mentor_overview: нет уроков после фильтрации")
        return {"total_students": len(students), "counts": {}, "by_lesson": {}, "by_student": {}, "items": []}

    # Карта student_id (внутренний) -> email
    student_id_to_email = {sid: s.user_email for sid, s in students.items()}

    # ВАЖНО: Передаем GetCourse ID уроков (Integer), а не внутренние Lesson.id
    # Безопасное преобразование с обработкой ошибок для нечисловых lesson_id
    lesson_getcourse_ids = [lid for lid in (_safe_int_lesson_id(l.lesson_id) for l in lessons) if lid is not None]

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] build_mentor_overview: GetCourse ID уроков для поиска ответов: {lesson_getcourse_ids}")

    earliest = await _fetch_logs_earliest_by_student_lesson(session, student_id_to_email, lesson_getcourse_ids)

    # ВАЖНО: Используем UTC timezone-aware datetime для корректного сравнения с данными из БД
    now_utc = datetime.now(pytz.UTC)

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] build_mentor_overview: текущее время UTC={now_utc}")

    items: List[LessonStatus] = []
    lessons_filtered: List[Lesson] = []
    for sid in students.keys():
        for lesson in lessons:
            deadline = _resolve_deadline(lesson)
            # ВАЖНО: Используем GetCourse ID урока для поиска в словаре earliest
            # Безопасное преобразование с обработкой ошибок для нечисловых lesson_id
            lesson_getcourse_id = _safe_int_lesson_id(lesson.lesson_id)
            if lesson_getcourse_id is None:
                logger.warning(f"Пропущен урок с некорректным lesson_id '{lesson.lesson_id}' (id={lesson.id})")
                continue
            answer_date = earliest.get((sid, lesson_getcourse_id))

            # убрать\закомментировать логирование после тестирования
            # if answer_date:
            #     logger.debug(f"[DEBUG] build_mentor_overview: студент {sid}, урок {lesson.lesson_id} (id={lesson.id}): найден ответ {answer_date}")

            # Исключаем уроки в состоянии not_started, если не требуется включать
            # ВАЖНО: Передаем UTC datetime для корректного определения состояния
            lesson_state = get_lesson_state(lesson, now_utc)

            # убрать\закомментировать логирование после тестирования
            # logger.debug(f"[DEBUG] build_mentor_overview: студент {sid}, урок {lesson.lesson_id} (id={lesson.id}): состояние={lesson_state}, "
            #             f"deadline={deadline}, answer_date={answer_date}")

            if not include_not_started and lesson_state == "not_started":
                # убрать\закомментировать логирование после тестирования
                # logger.debug(f"[DEBUG] build_mentor_overview: пропущен урок {lesson.lesson_id} (not_started)")
                continue

            # ВАЖНО: Передаем UTC datetime для корректного сравнения с дедлайнами из БД
            status = categorize_status(deadline, answer_date, now_utc)

            if status_filter and status != status_filter:
                continue

            items.append(LessonStatus(student_id=sid, lesson_id=lesson.id, status=status, deadline=deadline, answer_date=answer_date))
            lessons_filtered.append(lesson)

    # Агрегации
    counts = Counter(ls.status for ls in items)

    by_lesson: Dict[int, Counter] = defaultdict(Counter)
    by_student: Dict[int, Counter] = defaultdict(Counter)
    for ls in items:
        by_lesson[ls.lesson_id][ls.status] += 1
        by_student[ls.student_id][ls.status] += 1

    # Определяем состояние урока для заголовков
    lesson_state = None
    if lesson_id is not None and lessons:
        lesson_obj = next((l for l in lessons if l.id == lesson_id), None)
        if lesson_obj:
            # ВАЖНО: Используем UTC datetime для корректного определения состояния
            lesson_state = get_lesson_state(lesson_obj, now_utc)

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] build_mentor_overview: итоговые данные - студентов: {len(students)}, уроков: {len(lessons)}, items: {len(items)}")

    return {
        "total_students": len(students),
        "counts": dict(counts),
        "by_lesson": {lid: dict(c) for lid, c in by_lesson.items()},
        "by_student": {sid: dict(c) for sid, c in by_student.items()},
        "items": [ls.__dict__ for ls in items],
        "students": {sid: {"first_name": students[sid].first_name, "last_name": students[sid].last_name} for sid in students},
        "applied_filters": {
            "training_id": training_id,  # Оставляем для совместимости, но не используем
            "lesson_id": lesson_id,
            "status": status_filter,
            "lesson_state": lesson_state,
        },
    }


async def build_admin_overview(
    session: AsyncSession,
    training_id: Optional[int] = None,
    lesson_id: Optional[int] = None,
    include_not_started: bool = False,
) -> Dict[str, object]:
    """
    Возвращает агрегаты по наставникам и урокам для администратора.

    Args:
        session: Сессия БД
        training_id: Внутренний ID тренинга (Training.id) - опционально
        lesson_id: Внутренний ID урока (Lesson.id) - опционально
        include_not_started: Включать ли уроки в состоянии not_started

    Returns:
        Словарь с агрегированными данными по наставникам и урокам
    """
    # Текущее время для проверки актуальности записей
    now_utc = datetime.now(pytz.UTC)

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] build_admin_overview: training_id={training_id}, lesson_id={lesson_id}")

    # Все наставники с проверкой актуальности
    mentors_res = await session.execute(
        select(Mentor).where(
            and_(
                Mentor.valid_from <= now_utc,
                Mentor.valid_to >= now_utc
            )
        )
    )
    mentors: List[Mentor] = mentors_res.scalars().all()

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] build_admin_overview: найдено активных наставников: {len(mentors)}")

    if not mentors:
        return {"mentors": {}, "lessons": {}}

    result_by_mentor: Dict[int, Dict[str, object]] = {}
    global_lesson_counts: Dict[int, Counter] = defaultdict(Counter)

    for m in mentors:
        # убрать\закомментировать логирование после тестирования
        # logger.debug(f"[DEBUG] build_admin_overview: обработка наставника id={m.id}, mentor_id (GetCourse)={m.mentor_id}")

        # Для каждого наставника строим локальную сводку (с учётом фильтров)
        mentor_summary = await build_mentor_overview(
            session=session,
            mentor_id=m.id,
            training_id=training_id,
            lesson_id=lesson_id,
            include_not_started=include_not_started,
        )
        result_by_mentor[m.id] = {
            "counts": mentor_summary.get("counts", {}),
            "total_students": mentor_summary.get("total_students", 0),
        }

        # Копим глобальную статистику по урокам
        for lesson_id_key, counter in mentor_summary.get("by_lesson", {}).items():
            global_lesson_counts[int(lesson_id_key)].update(counter)

    lessons_agg = {lid: dict(cnt) for lid, cnt in global_lesson_counts.items()}

    # убрать\закомментировать логирование после тестирования
    # logger.debug(f"[DEBUG] build_admin_overview: итоговые данные - наставников: {len(result_by_mentor)}, уроков: {len(lessons_agg)}")

    return {
        "mentors": result_by_mentor,
        "lessons": lessons_agg,
    }
