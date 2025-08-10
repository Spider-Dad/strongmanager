from __future__ import annotations

import logging
from collections import defaultdict, Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Iterable, Set

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.database import (
    Mentor,
    Student,
    Mapping,
    Training,
    Lesson,
    Log,
    ProgressConfig,
    ProgressOverride,
)

logger = logging.getLogger(__name__)


# Статусы табеля
STATUS_ON_TIME = "on_time"  # сдал вовремя
STATUS_LATE = "late"  # сдал с опозданием
STATUS_NO_BEFORE_DEADLINE = "no_before_deadline"  # не сдал, дедлайн не прошёл
STATUS_NO_AFTER_DEADLINE = "no_after_deadline"  # не сдал, дедлайн прошёл

NOT_ON_TIME_SET = {STATUS_LATE, STATUS_NO_BEFORE_DEADLINE, STATUS_NO_AFTER_DEADLINE}


@dataclass
class LessonStatus:
    student_id: int
    lesson_id: int
    status: str
    deadline: Optional[datetime]
    answer_date: Optional[datetime]


def categorize_status(deadline: Optional[datetime], earliest_answer_date: Optional[datetime], now: Optional[datetime] = None) -> str:
    """Возвращает один из статусов STATUS_* по дедлайну и дате ответа.

    Правила:
    - Нет ответа: now < deadline → no_before_deadline; иначе → no_after_deadline
    - Есть ответ: answer_date ≤ deadline → on_time; иначе → late
    - Если дедлайн отсутствует: считаем, что срок не истёк → no_before_deadline (консервативно)
    """
    current_time = now or datetime.now()

    if deadline is None:
        return STATUS_NO_BEFORE_DEADLINE if earliest_answer_date is None else STATUS_ON_TIME

    if earliest_answer_date is None:
        return STATUS_NO_BEFORE_DEADLINE if current_time < deadline else STATUS_NO_AFTER_DEADLINE

    return STATUS_ON_TIME if earliest_answer_date <= deadline else STATUS_LATE


async def _fetch_students_for_mentor(session: AsyncSession, mentor_id: int) -> Dict[int, Student]:
    mapping_rows = await session.execute(
        select(Mapping.student_id).where(Mapping.mentor_id == mentor_id)
    )
    student_ids = [row[0] for row in mapping_rows.fetchall()]
    if not student_ids:
        return {}

    students_res = await session.execute(select(Student).where(Student.id.in_(student_ids)))
    students: List[Student] = students_res.scalars().all()
    return {s.id: s for s in students}


async def _fetch_trainings_for_mentor(session: AsyncSession, mentor_id: int) -> Set[int]:
    mapping_rows = await session.execute(
        select(Mapping.training_id).where(Mapping.mentor_id == mentor_id)
    )
    return {row[0] for row in mapping_rows.fetchall()}


async def _fetch_lessons_for_trainings(session: AsyncSession, training_ids: Iterable[int]) -> List[Lesson]:
    if not training_ids:
        return []
    result = await session.execute(select(Lesson).where(Lesson.training_id.in_(list(training_ids))))
    return result.scalars().all()


async def _fetch_progress_config(session: AsyncSession, training_ids: Iterable[int], lesson_ids: Iterable[int]) -> Tuple[Dict[int, ProgressConfig], Dict[int, ProgressConfig]]:
    """Возвращает два словаря: конфигурации по урокам и по тренингам.
    lesson_config[lesson_id] = ProgressConfig; training_config[training_id] = ProgressConfig
    Если несколько записей, приоритет не гарантируем — рекомендуется уникальность в источнике.
    """
    lesson_ids = list(set(lesson_ids))
    training_ids = list(set(training_ids))

    lesson_config: Dict[int, ProgressConfig] = {}
    training_config: Dict[int, ProgressConfig] = {}

    if training_ids:
        res_tr = await session.execute(select(ProgressConfig).where(ProgressConfig.training_id.in_(training_ids)))
        for cfg in res_tr.scalars().all():
            if cfg.lesson_id:
                lesson_config[cfg.lesson_id] = cfg
            else:
                training_config[cfg.training_id] = cfg

    return lesson_config, training_config


async def _fetch_overrides(session: AsyncSession, student_ids: Iterable[int], lesson_ids: Iterable[int]) -> Dict[Tuple[int, int], ProgressOverride]:
    key_to_override: Dict[Tuple[int, int], ProgressOverride] = {}
    ids_s = list(set(student_ids))
    ids_l = list(set(lesson_ids))
    if not ids_s or not ids_l:
        return key_to_override
    res = await session.execute(
        select(ProgressOverride).where(
            and_(
                ProgressOverride.student_id.in_(ids_s),
                ProgressOverride.lesson_id.in_(ids_l),
            )
        )
    )
    now = datetime.now()
    for po in res.scalars().all():
        if po.expires_at is None or po.expires_at > now:
            key_to_override[(po.student_id, po.lesson_id)] = po
    return key_to_override


async def _fetch_logs_earliest_by_student_lesson(
    session: AsyncSession,
    student_id_to_email: Dict[int, str],
    lesson_ids: Iterable[int],
) -> Dict[Tuple[int, int], datetime]:
    """Возвращает (student_id, lesson_id) -> earliest_answer_date по email студента и lesson_id.
    Сопоставление по email (в `logs.user_email`).
    """
    emails = list({e for e in student_id_to_email.values() if e})
    lesson_ids_list = list(set(lesson_ids))
    if not emails or not lesson_ids_list:
        return {}

    res = await session.execute(
        select(Log.user_email, Log.answer_lesson_id, func.min(Log.date))
        .where(
            and_(
                Log.user_email.in_(emails),
                Log.answer_lesson_id.in_(lesson_ids_list),
            )
        )
        .group_by(Log.user_email, Log.answer_lesson_id)
    )

    email_to_student = {email: sid for sid, email in student_id_to_email.items() if email}

    earliest: Dict[Tuple[int, int], datetime] = {}
    for user_email, lesson_id, min_date in res.fetchall():
        student_id = email_to_student.get(user_email)
        if student_id is not None and min_date is not None:
            earliest[(student_id, lesson_id)] = min_date
    return earliest


def _resolve_deadline(lesson: Lesson, lesson_cfg: Optional[ProgressConfig], training_cfg: Optional[ProgressConfig]) -> Optional[datetime]:
    if lesson_cfg and lesson_cfg.deadline_override:
        return lesson_cfg.deadline_override
    if training_cfg and training_cfg.deadline_override:
        return training_cfg.deadline_override
    return lesson.deadline_date


async def build_mentor_overview(
    session: AsyncSession,
    mentor_id: int,
    training_id: Optional[int] = None,
    lesson_id: Optional[int] = None,
    status_filter: Optional[str] = None,
) -> Dict[str, object]:
    """Возвращает агрегированную сводку для наставника по его студентам.
    Фильтры: training_id, lesson_id, status_filter (один из STATUS_*).
    """
    students = await _fetch_students_for_mentor(session, mentor_id)
    if not students:
        return {"total_students": 0, "counts": {}, "by_lesson": {}, "by_student": {}, "items": []}

    # Ограничиваем тренинги по фильтру, иначе берём все закрепления
    mentor_training_ids = await _fetch_trainings_for_mentor(session, mentor_id)
    if training_id is not None:
        training_ids = {tid for tid in mentor_training_ids if tid == training_id}
    else:
        training_ids = mentor_training_ids

    lessons = await _fetch_lessons_for_trainings(session, training_ids)
    if lesson_id is not None:
        lessons = [l for l in lessons if l.id == lesson_id]

    if not lessons:
        return {"total_students": len(students), "counts": {}, "by_lesson": {}, "by_student": {}, "items": []}

    lesson_config, training_config = await _fetch_progress_config(session, training_ids, [l.id for l in lessons])

    # Карта student_id -> email
    student_id_to_email = {sid: s.user_email for sid, s in students.items()}

    earliest = await _fetch_logs_earliest_by_student_lesson(session, student_id_to_email, [l.id for l in lessons])
    overrides = await _fetch_overrides(session, students.keys(), [l.id for l in lessons])

    now = datetime.now()

    items: List[LessonStatus] = []
    for sid in students.keys():
        for lesson in lessons:
            # Пропускаем уроки скрытые видимостью
            l_cfg = lesson_config.get(lesson.id)
            t_cfg = training_config.get(lesson.training_id)
            if (l_cfg and l_cfg.visibility == "hidden") or (t_cfg and t_cfg.visibility == "hidden"):
                continue

            deadline = _resolve_deadline(lesson, l_cfg, t_cfg)
            answer_date = earliest.get((sid, lesson.id))
            status = categorize_status(deadline, answer_date, now)

            ov = overrides.get((sid, lesson.id))
            if ov and ov.status_override:
                status = ov.status_override

            if status_filter and status != status_filter:
                continue

            items.append(LessonStatus(student_id=sid, lesson_id=lesson.id, status=status, deadline=deadline, answer_date=answer_date))

    # Агрегации
    counts = Counter(ls.status for ls in items)

    by_lesson: Dict[int, Counter] = defaultdict(Counter)
    by_student: Dict[int, Counter] = defaultdict(Counter)
    for ls in items:
        by_lesson[ls.lesson_id][ls.status] += 1
        by_student[ls.student_id][ls.status] += 1

    return {
        "total_students": len(students),
        "counts": dict(counts),
        "by_lesson": {lid: dict(c) for lid, c in by_lesson.items()},
        "by_student": {sid: dict(c) for sid, c in by_student.items()},
        "items": [ls.__dict__ for ls in items],
    }


async def build_admin_overview(
    session: AsyncSession,
    training_id: Optional[int] = None,
    lesson_id: Optional[int] = None,
) -> Dict[str, object]:
    """Возвращает агрегаты по наставникам и урокам для администратора."""
    # Все наставники
    mentors_res = await session.execute(select(Mentor))
    mentors: List[Mentor] = mentors_res.scalars().all()
    if not mentors:
        return {"mentors": {}, "lessons": {}}

    result_by_mentor: Dict[int, Dict[str, object]] = {}
    global_lesson_counts: Dict[int, Counter] = defaultdict(Counter)

    for m in mentors:
        # Для каждого наставника строим локальную сводку (с учётом фильтров)
        mentor_summary = await build_mentor_overview(
            session=session,
            mentor_id=m.id,
            training_id=training_id,
            lesson_id=lesson_id,
        )
        result_by_mentor[m.id] = {
            "counts": mentor_summary.get("counts", {}),
            "total_students": mentor_summary.get("total_students", 0),
        }

        # Копим глобальную статистику по урокам
        for lesson_id_key, counter in mentor_summary.get("by_lesson", {}).items():
            global_lesson_counts[int(lesson_id_key)].update(counter)

    lessons_agg = {lid: dict(cnt) for lid, cnt in global_lesson_counts.items()}

    return {
        "mentors": result_by_mentor,
        "lessons": lessons_agg,
    }
