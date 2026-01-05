import logging
from aiogram import types
from aiogram.dispatcher import Dispatcher
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from typing import Optional
from sqlalchemy import select, and_

from bot.services.database import get_session

logger = logging.getLogger(__name__)

from bot.services.gradebook_service import (
    build_mentor_overview,
    STATUS_ON_TIME,
    STATUS_LATE,
    STATUS_NO_BEFORE_DEADLINE,
    STATUS_NO_AFTER_DEADLINE,
    STATUS_HAS_ANSWER,
    STATUS_NO_ANSWER,
    simplify_status,
    get_status_emoji,
    get_lesson_state,
)
from bot.utils.markdown import escape_markdown_v2, bold, italic
from bot.keyboards.gradebook import (
    kb_progress_filters,
    kb_filters_with_pagination,
    _kb_lesson_select_with_pagination,
)


def _simplify_counters(counters: dict) -> dict:
    """
    Преобразует детальные счетчики статусов в упрощенный формат.

    Args:
        counters: Словарь с детальными статусами {STATUS_ON_TIME: N, STATUS_LATE: M, ...}

    Returns:
        Словарь с упрощенными статусами {STATUS_HAS_ANSWER: X, STATUS_NO_ANSWER: Y}
    """
    has_answer = counters.get(STATUS_ON_TIME, 0) + counters.get(STATUS_LATE, 0)
    no_answer = counters.get(STATUS_NO_BEFORE_DEADLINE, 0) + counters.get(STATUS_NO_AFTER_DEADLINE, 0)
    return {
        STATUS_HAS_ANSWER: has_answer,
        STATUS_NO_ANSWER: no_answer,
    }


async def cmd_progress(message: types.Message, config):
    user_id = message.from_user.id
    # Наставник — не админ
    if user_id in config.admin_ids:
        await message.answer(escape_markdown_v2("Вы выбрали команду для Наставника. Для просмотра табеля успеваемости, для вашей роли, используйте команду /progress_admin"), parse_mode='MarkdownV2')
        return

    async for session in get_session():
        # Определим mentor_id по telegram_id
        from sqlalchemy import select
        from bot.services.database import Mentor
        res = await session.execute(select(Mentor).where(Mentor.telegram_id == user_id))
        mentor = res.scalars().first()
        if not mentor:
            await message.answer("Доступ запрещён. Требуется авторизация как наставник.")
            return

        await _render_students_list(message, session, mentor_id=mentor.id, training_id=None, lesson_id=None, page=1)


async def cmd_progress_admin(message: types.Message, config):
    user_id = message.from_user.id
    if user_id not in config.admin_ids:
        await message.answer(escape_markdown_v2("Вы выбрали команду для Администратора. Для просмотра табеля успеваемости, для вашей роли, используйте команду /progress"), parse_mode='MarkdownV2')
        return

    async for session in get_session():
        await _render_admin_list(message, session, training_id=None, lesson_id=None, page=1)


# Функции _kb_progress_filters_with_tr и _kb_lesson_select удалены - больше не используются


# Функция _format_summary_text больше не используется


async def cb_progress_router(call: CallbackQuery, config):
    user_id = call.from_user.id
    data = call.data or ""

    async for session in get_session():
        # Проверяем: админ или наставник
        is_admin = user_id in config.admin_ids

        from sqlalchemy import select
        from bot.services.database import Mentor, Mapping, Training, Lesson

        mentor = None
        if not is_admin:
            res = await session.execute(select(Mentor).where(Mentor.telegram_id == user_id))
            mentor = res.scalars().first()
            if not mentor:
                await call.answer("Нет доступа", show_alert=True)
                return

        # Фильтр по тренингам убран - больше не используется

        # Показ списка студентов (детализация): gb:list:students [опц. фильтры + пагинация]
        if data.startswith("gb:list:students") or data.startswith("gb:page:students"):
            # Немедленно отвечаем на callback query
            await call.answer("Загрузка...")

            # Парсим параметры: gb:list:students[:tr:{id}][:lesson:{id}][:p:{page}]
            parts = data.split(":")
            training_id = None
            lesson_id = None
            page = 1
            if "tr" in parts:
                try:
                    training_id = int(parts[parts.index("tr") + 1])
                except Exception:
                    training_id = None
            if "lesson" in parts:
                try:
                    lesson_id = int(parts[parts.index("lesson") + 1])
                except Exception:
                    lesson_id = None
            if "p" in parts:
                try:
                    page = int(parts[parts.index("p") + 1])
                except Exception:
                    page = 1

            try:
                summary = await build_mentor_overview(session, mentor_id=mentor.id, training_id=training_id, lesson_id=lesson_id)

                # Счётчики по студентам: подсчёт статусов по items с преобразованием в упрощенный формат
                per_student = {}
                for it in summary.get("items", []):
                    sid = it.get("student_id") if isinstance(it, dict) else it.student_id
                    st = it.get("status") if isinstance(it, dict) else it.status
                    simplified_status = simplify_status(st)
                    if simplified_status is None:
                        continue  # Пропускаем STATUS_OPTIONAL и другие
                    if sid not in per_student:
                        per_student[sid] = {
                            STATUS_HAS_ANSWER: 0,
                            STATUS_NO_ANSWER: 0,
                        }
                    per_student[sid][simplified_status] += 1

                # Сортировка по фамилии, затем имени
                students = summary.get("students", {})
                def sort_key(sid):
                    info = students.get(sid, {})
                    last = (info.get("last_name") or "").lower()
                    first = (info.get("first_name") or "").lower()
                    return (last, first, sid)
                ordered_ids = sorted(per_student.keys(), key=sort_key)

                # Пагинация: группируем карточки целиком (строка = одна карточка)
                page_size = 20
                total_pages = max(1, (len(ordered_ids) + page_size - 1) // page_size)
                page = max(1, min(page, total_pages))
                start = (page - 1) * page_size
                end = start + page_size
                page_ids = ordered_ids[start:end]

                # Используем полный хедер с легендой
                lines = await _build_header_with_legend(session, training_id, lesson_id, is_admin=is_admin)

                for sid in page_ids:
                    info = students.get(sid, {})
                    last = info.get("last_name") or ""
                    first = info.get("first_name") or ""
                    counters = per_student[sid]
                    student_name = f"{last} {first}"
                    lines.append(f"{italic('Студент')}: {escape_markdown_v2(student_name)}")
                    lines.append(escape_markdown_v2(f"✅ - {counters.get(STATUS_HAS_ANSWER, 0)} | ❌ - {counters.get(STATUS_NO_ANSWER, 0)}"))
                    lines.append("")  # Пустая строка для разделения студентов

                text = "\n".join(lines)

                # Построение базового префикса для пагинации
                base = "gb:page:students"
                if training_id is not None:
                    base += f":tr:{training_id}"
                if lesson_id is not None:
                    base += f":lesson:{lesson_id}"

                await call.message.edit_text(text, parse_mode='MarkdownV2')
                await call.message.edit_reply_markup(reply_markup=kb_filters_with_pagination(training_id, lesson_id, page, total_pages, base))
            except Exception as e:
                logger.error(f"Ошибка при рендеринге списка студентов: {e}")
                await call.message.edit_text("❌ Произошла ошибка при загрузке данных — попробуйте еще раз")
            return

        # Пагинация в админском режиме: gb:page:admin[:tr:{id}][:lesson:{id}][:p:{page}]
        if data.startswith("gb:page:admin"):
            # Немедленно отвечаем на callback query, чтобы избежать таймаута
            await call.answer("Загрузка...")

            parts = data.split(":")
            training_id = None
            lesson_id = None
            page = 1
            if "tr" in parts:
                try:
                    training_id = int(parts[parts.index("tr") + 1])
                except Exception:
                    training_id = None
            if "lesson" in parts:
                try:
                    lesson_id = int(parts[parts.index("lesson") + 1])
                except Exception:
                    lesson_id = None
            if "p" in parts:
                try:
                    page = int(parts[parts.index("p") + 1])
                except Exception:
                    page = 1

            try:
                await _render_admin_list(call.message, session, training_id=training_id, lesson_id=lesson_id, page=page, edit=True)
            except Exception as e:
                logger.error(f"Ошибка при рендеринге админского списка: {e}")
                await call.message.edit_text("❌ Произошла ошибка при загрузке данных — попробуйте еще раз")
            return

        # Установка тренинга убрана - больше не используется

        # Выбор урока: gb:filter:lesson[:p:{page}]
        if data.startswith("gb:filter:lesson"):
            # Немедленно отвечаем на callback query
            await call.answer("Загрузка...")

            parts = data.split(":")
            page = 1
            # Проверяем наличие параметра страницы: gb:filter:lesson:p:page
            if len(parts) >= 5 and parts[3] == "p":
                try:
                    page = int(parts[4])
                except Exception:
                    page = 1

            try:
                if is_admin:
                    await _render_lessons_list(call.message, session, mentor_id=None, page=page, edit=True)
                else:
                    await _render_lessons_list(call.message, session, mentor_id=mentor.id, page=page, edit=True)
            except Exception as e:
                logger.error(f"Ошибка при выборе урока: {e}")
                await call.answer("Произошла ошибка при загрузке уроков", show_alert=True)
            return

        # Пагинация уроков: gb:page:lessons:p:{page}
        if data.startswith("gb:page:lessons"):
            # Немедленно отвечаем на callback query
            await call.answer("Загрузка...")

            parts = data.split(":")
            # Проверяем формат: gb:page:lessons:p:page
            if len(parts) < 5 or parts[2] != "lessons" or parts[3] != "p":
                await call.answer("Некорректные данные", show_alert=True)
                return

            try:
                page = int(parts[4])
            except Exception:
                await call.answer("Некорректные данные", show_alert=True)
                return

            try:
                if is_admin:
                    await _render_lessons_list(call.message, session, mentor_id=None, page=page, edit=True)
                else:
                    await _render_lessons_list(call.message, session, mentor_id=mentor.id, page=page, edit=True)
            except Exception as e:
                logger.error(f"Ошибка при пагинации уроков: {e}")
                await call.answer("Произошла ошибка при загрузке уроков", show_alert=True)
            return

        # Установка урока: gb:set:lesson:{lesson_id}[:tr:{training_id}] (training_id оставлен для совместимости)
        if data.startswith("gb:set:lesson:"):
            # Немедленно отвечаем на callback query
            await call.answer("Загрузка...")

            parts = data.split(":")
            # Проверяем формат: gb:set:lesson:LESSON_ID[:tr:TRAINING_ID]
            # training_id оставлен для совместимости, но не используется
            try:
                lesson_id = int(parts[3])
                training_id = None
                # Поддерживаем старый формат с training_id для совместимости
                if len(parts) >= 6 and parts[4] == "tr":
                    try:
                        training_id = int(parts[5])
                    except Exception:
                        pass
            except Exception:
                await call.answer("Некорректные данные", show_alert=True)
                return

            try:
                if is_admin:
                    await _render_admin_list(call.message, session, training_id=None, lesson_id=lesson_id, page=1, edit=True)
                else:
                    await _render_students_list(call.message, session, mentor_id=mentor.id, training_id=None, lesson_id=lesson_id, page=1, edit=True)
            except Exception as e:
                logger.error(f"Ошибка при рендеринге списка: {e}")
                await call.message.edit_text("❌ Произошла ошибка при загрузке данных. Попробуйте еще раз.")
            return

        # Блокировка выбора not_started
        if data == "gb:block:not_started":
            await call.answer("Статистика доступна только по активным и завершенным тренингам/урокам", show_alert=True)
            return

        if data == "gb:back":
            # Немедленно отвечаем на callback query
            await call.answer("Загрузка...")

            try:
                # Сброс к базовому экрану
                if is_admin:
                    await _render_admin_list(call.message, session, training_id=None, lesson_id=None, page=1, edit=True)
                else:
                    await _render_students_list(call.message, session, mentor_id=mentor.id, training_id=None, lesson_id=None, page=1, edit=True)
            except Exception as e:
                logger.error(f"Ошибка при рендеринге списка: {e}")
                # Fallback: отправляем простое сообщение без MarkdownV2
                try:
                    await call.message.edit_text("❌ Произошла ошибка при загрузке данных — попробуйте еще раз")
                except Exception as fallback_error:
                    logger.error(f"Ошибка при отправке fallback сообщения: {fallback_error}")
                    # Последняя попытка - отвечаем на callback query
                    await call.answer("Произошла ошибка. Попробуйте позже.", show_alert=True)
            return

        if data == "gb:nop":
            await call.answer()
            return


def register_gradebook_handlers(dp: Dispatcher, config):
    dp.register_message_handler(lambda msg: cmd_progress(msg, config), commands=["progress"], state="*")
    dp.register_message_handler(lambda msg: cmd_progress_admin(msg, config), commands=["progress_admin"], state="*")
    dp.register_callback_query_handler(lambda c: cb_progress_router(c, config), lambda c: c.data and c.data.startswith("gb:"), state="*")


from typing import Optional


async def _build_header_with_legend(session, training_id: Optional[int], lesson_id: Optional[int], is_admin: bool = False) -> list[str]:
    """Формирует хедер с легендой для отображения статистики."""
    # Определяем строку с уроком
    if lesson_id is None:
        lesson_line = escape_markdown_v2("по всем активным и завершенным урокам")
    else:
        from sqlalchemy import select
        from bot.services.database import Lesson
        lr = await session.execute(select(Lesson).where(Lesson.id == lesson_id))
        l = lr.scalars().first()
        if l:
            # ВАЖНО: В модели Lesson поле называется lesson_title, а не title
            title_text = l.lesson_title if l.lesson_title else str(lesson_id)
            lesson_line = escape_markdown_v2(title_text)
        else:
            lesson_line = escape_markdown_v2(str(lesson_id))

    title = "📈 " + bold("Статистика по наставникам") if is_admin else "📊 " + bold("Статистика ваших студентов")

    return [
        title,
        "",
        lesson_line,
        "",
        escape_markdown_v2("✅ Есть ответ | ❌ Нет ответа"),
        "",
    ]


async def _render_lessons_list(message: types.Message, session, mentor_id: Optional[int] = None, page: int = 1, *, edit: bool = False):
    """Рендерит список уроков с пагинацией. Получает все уроки всех тренингов наставника."""
    from sqlalchemy import select, and_
    from bot.services.database import Lesson, Training, Mapping, Mentor
    from bot.services.gradebook_service import get_lesson_state, get_status_emoji, _fetch_trainings_for_mentor, _fetch_lessons_for_trainings
    from datetime import datetime
    import pytz
    now_utc = datetime.now(pytz.UTC)

    try:
        # Получаем тренинги наставника (или все тренинги для админа)
        if mentor_id is None:
            # Админ - получаем все тренинги
            trainings_res = await session.execute(
                select(Training).where(
                    and_(
                        Training.valid_from <= now_utc,
                        Training.valid_to >= now_utc
                    )
                )
            )
            trainings = trainings_res.scalars().all()
            training_getcourse_ids = {t.training_id for t in trainings}
        else:
            # Наставник - получаем тренинги через функцию
            training_getcourse_ids = await _fetch_trainings_for_mentor(session, mentor_id)

        if not training_getcourse_ids:
            await message.edit_text("Нет доступных уроков")
            return

        # Получаем все уроки всех тренингов
        lessons = await _fetch_lessons_for_trainings(session, training_getcourse_ids)
        if not lessons:
            await message.edit_text("Нет доступных уроков")
            return

        # Сортируем уроки по дате открытия (opening_date)
        lesson_data = []
        for l in lessons:
            state = get_lesson_state(l, now_utc)
            state_emoji = get_status_emoji(state)
            allowed = state != "not_started"  # Только активные и завершенные доступны
            # ВАЖНО: В модели Lesson поле называется lesson_title, а не title
            lesson_title = l.lesson_title or f"Lesson {l.id}"
            title = f"{state_emoji} {lesson_title}"
            # Сортировка по opening_date (по возрастанию, None в конец)
            opening_date = l.opening_date
            sort_key = (opening_date is None, opening_date or datetime.max.replace(tzinfo=pytz.UTC))
            lesson_data.append((l.id, title, allowed, sort_key))

        # Сортируем по opening_date
        lesson_data.sort(key=lambda x: x[3])

        # Пагинация
        page_size = 10
        total_pages = max(1, (len(lesson_data) + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        end = start + page_size
        page_lessons = lesson_data[start:end]

        # Формируем опции для клавиатуры
        opts = [(lesson_id, title, allowed) for lesson_id, title, allowed, _ in page_lessons]

        # Создаем клавиатуру с пагинацией (training_id оставлен для совместимости, но не используется)
        kb = _kb_lesson_select_with_pagination(opts, None, page, total_pages)

        if edit:
            await message.edit_reply_markup(reply_markup=kb)
        else:
            await message.answer("Выберите урок:", reply_markup=kb)

    except Exception as e:
        logger.error(f"Ошибка при рендеринге списка уроков: {e}")
        if edit:
            await message.edit_text("❌ Произошла ошибка при загрузке уроков")
        else:
            await message.answer("❌ Произошла ошибка при загрузке уроков")


async def _render_students_list(message: types.Message, session, mentor_id: int, training_id: Optional[int], lesson_id: Optional[int], page: int, *, edit: bool = False):
    from bot.services.gradebook_service import build_mentor_overview
    summary = await build_mentor_overview(session, mentor_id=mentor_id, training_id=training_id, lesson_id=lesson_id, include_not_started=False)

    # counters per student с преобразованием в упрощенный формат
    per_student = {}
    for it in summary.get("items", []):
        sid = it.get("student_id") if isinstance(it, dict) else it.student_id
        st = it.get("status") if isinstance(it, dict) else it.status
        simplified_status = simplify_status(st)
        if simplified_status is None:
            continue  # Пропускаем STATUS_OPTIONAL и другие
        per_student.setdefault(sid, {
            STATUS_HAS_ANSWER: 0,
            STATUS_NO_ANSWER: 0,
        })[simplified_status] += 1

    # order students
    students = summary.get("students", {})
    def sort_key(sid):
        info = students.get(sid, {})
        last = (info.get("last_name") or "").lower()
        first = (info.get("first_name") or "").lower()
        return (last, first, sid)
    ordered_ids = sorted(per_student.keys(), key=sort_key)

    # Проверка наличия студентов
    if not ordered_ids:
        text = "📊 " + bold("Статистика ваших студентов") + "\n\n" + escape_markdown_v2("Нет назначенных студентов")
        try:
            await message.edit_text(text, parse_mode='MarkdownV2', reply_markup=kb_progress_filters())
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения 'Нет студентов': {e}")
            # Fallback: отправляем без MarkdownV2
            await message.edit_text("📊 Статистика ваших студентов\n\nНет назначенных студентов", reply_markup=kb_progress_filters())
        return

    # paging
    page_size = 20
    total_pages = max(1, (len(ordered_ids) + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    page_ids = ordered_ids[start:end]

    lines = await _build_header_with_legend(session, training_id, lesson_id, is_admin=False)
    for sid in page_ids:
        info = students.get(sid, {})
        last = info.get("last_name") or ""
        first = info.get("first_name") or ""
        counters = per_student[sid]
        student_name = f"{last} {first}"
        lines.append(f"{italic('Студент')}: {escape_markdown_v2(student_name)}")
        lines.append(escape_markdown_v2(f"✅ - {counters.get(STATUS_HAS_ANSWER, 0)} | ❌ - {counters.get(STATUS_NO_ANSWER, 0)}"))
        lines.append("")  # Пустая строка для разделения студентов

    text = "\n".join(lines)
    base = "gb:page:students"
    if training_id is not None:
        base += f":tr:{training_id}"  # Оставлено для совместимости
    if lesson_id is not None:
        base += f":lesson:{lesson_id}"
    kb = kb_filters_with_pagination(training_id, lesson_id, page, total_pages, base)

    if edit:
        try:
            await message.edit_text(text, parse_mode='MarkdownV2')
            await message.edit_reply_markup(reply_markup=kb)
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения с MarkdownV2: {e}")
            # Fallback: отправляем без MarkdownV2
            try:
                # Убираем MarkdownV2 форматирование для fallback
                fallback_text = text.replace('*', '').replace('_', '').replace('\\', '')
                await message.edit_text(fallback_text)
                await message.edit_reply_markup(reply_markup=kb)
            except Exception as fallback_error:
                logger.error(f"Ошибка при fallback редактировании: {fallback_error}")
                # Последняя попытка - просто обновляем клавиатуру
                await message.edit_reply_markup(reply_markup=kb)
    else:
        try:
            await message.answer(text, reply_markup=kb)
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения с MarkdownV2: {e}")
            # Fallback: отправляем без MarkdownV2
            fallback_text = text.replace('*', '').replace('_', '').replace('\\', '')
            await message.answer(fallback_text, reply_markup=kb)


async def _render_admin_list(message: types.Message, session, training_id: Optional[int], lesson_id: Optional[int], page: int, *, edit: bool = False):
    from sqlalchemy import select, and_
    from bot.services.database import Mentor
    from datetime import datetime
    import pytz
    now_utc = datetime.now(pytz.UTC)

    # Все наставники с проверкой актуальности
    mentors_res = await session.execute(
        select(Mentor).where(
            and_(
                Mentor.valid_from <= now_utc,
                Mentor.valid_to >= now_utc
            )
        )
    )
    mentors = mentors_res.scalars().all()

    # Показываем индикатор загрузки для пользователя
    if edit:
        try:
            await message.edit_text("⏳ Загрузка данных…", parse_mode='MarkdownV2')
        except Exception:
            pass  # Игнорируем ошибки при обновлении сообщения

    blocks = []  # [(mentor_display, [(student_display, counters_dict), ...])]
    from bot.services.gradebook_service import build_mentor_overview
    for m in mentors:
        summary = await build_mentor_overview(session, mentor_id=m.id, training_id=training_id, lesson_id=lesson_id, include_not_started=False)
        students = summary.get("students", {})
        per_student = {}
        for it in summary.get("items", []):
            sid = it.get("student_id") if isinstance(it, dict) else it.student_id
            st = it.get("status") if isinstance(it, dict) else it.status
            simplified_status = simplify_status(st)
            if simplified_status is None:
                continue  # Пропускаем STATUS_OPTIONAL и другие
            per_student.setdefault(sid, {
                STATUS_HAS_ANSWER: 0,
                STATUS_NO_ANSWER: 0,
            })[simplified_status] += 1
        def s_key(sid):
            info = students.get(sid, {})
            return ((info.get("last_name") or "").lower(), (info.get("first_name") or "").lower(), sid)
        ordered_ids = sorted(per_student.keys(), key=s_key)
        student_rows = []
        for sid in ordered_ids:
            info = students.get(sid, {})
            last = info.get("last_name") or ""
            first = info.get("first_name") or ""
            counters = per_student[sid]
            student_name = f"{last} {first}"
            student_title = f"{italic('Студент')}: {escape_markdown_v2(student_name)}"
            student_stats = escape_markdown_v2(f"✅ - {counters.get(STATUS_HAS_ANSWER, 0)} | ❌ - {counters.get(STATUS_NO_ANSWER, 0)}")
            student_rows.append((student_title, student_stats))
        mentor_last = m.last_name or ""
        mentor_first = m.first_name or ""
        mentor_full_name = f"{mentor_last} {mentor_first}".strip()
        mentor_name = f"{bold('Наставник')}: {escape_markdown_v2(mentor_full_name)}"
        if student_rows:  # Добавляем только наставников с назначенными студентами
            blocks.append((mentor_name, student_rows, len(student_rows)))

    if not blocks:
        text = "📈 " + bold("Статистика по наставникам") + "\n\n" + escape_markdown_v2("Статистика собирается только по активным и завершенным тренингам/урокам")
        try:
            await message.edit_text(text, parse_mode='MarkdownV2')
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения 'Нет блоков': {e}")
            # Fallback: отправляем без MarkdownV2
            await message.edit_text("📈 Статистика по наставникам\n\nСтатистика собирается только по активным и завершенным тренингам/урокам")
        return

    # Пагинация блоками (не разрываем наставника)
    page_size = 20
    pages = []
    current = []
    rows_used = 0
    for name, rows, count in blocks:
        if count > page_size:
            if current:
                pages.append(current)
                current = []
                rows_used = 0
            pages.append([(name, rows)])
            continue
        if rows_used + count > page_size:
            pages.append(current)
            current = []
            rows_used = 0
        current.append((name, rows))
        rows_used += count
    if current:
        pages.append(current)

    total_pages = max(1, len(pages))
    page = max(1, min(page, total_pages))
    page_blocks = pages[page - 1] if pages else []

    lines = await _build_header_with_legend(session, training_id, lesson_id, is_admin=True)
    for mentor_name, rows in page_blocks:
        lines.append(mentor_name)  # mentor_name уже отформатирован с bold() и escape_markdown_v2()
        lines.append("")  # Пустая строка для разделения от блока студентов
        for title, counters in rows:
            lines.append(title)  # title уже отформатирован с italic() и escape_markdown_v2()
            lines.append(counters)  # counters уже экранированы
            lines.append("")  # Пустая строка для разделения студентв между собой
        lines.append(escape_markdown_v2("-----"))  # строка для разделения наставников между собой

    text = "\n".join(lines)
    base = "gb:page:admin"
    if training_id is not None:
        base += f":tr:{training_id}"  # Оставлено для совместимости
    if lesson_id is not None:
        base += f":lesson:{lesson_id}"
    kb = kb_filters_with_pagination(training_id, lesson_id, page, total_pages, base)

    if edit:
        try:
            await message.edit_text(text)
            await message.edit_reply_markup(reply_markup=kb)
        except Exception as e:
            logger.error(f"Ошибка при редактировании админского сообщения: {e}")
            # Fallback: отправляем без MarkdownV2
            try:
                fallback_text = text.replace('*', '').replace('_', '').replace('\\', '')
                await message.edit_text(fallback_text)
                await message.edit_reply_markup(reply_markup=kb)
            except Exception as fallback_error:
                logger.error(f"Ошибка при fallback редактировании админского сообщения: {fallback_error}")
                # Последняя попытка - просто обновляем клавиатуру
                await message.edit_reply_markup(reply_markup=kb)
    else:
        try:
            await message.answer(text, reply_markup=kb)
        except Exception as e:
            logger.error(f"Ошибка при отправке админского сообщения: {e}")
            # Fallback: отправляем без MarkdownV2
            fallback_text = text.replace('*', '').replace('_', '').replace('\\', '')
            await message.answer(fallback_text, reply_markup=kb)