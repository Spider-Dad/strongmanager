import logging
from aiogram import types
from aiogram.dispatcher import Dispatcher
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from typing import Optional

from bot.services.database import get_session

logger = logging.getLogger(__name__)

from bot.services.gradebook_service import (
    build_mentor_overview,
    build_admin_overview,
    STATUS_ON_TIME,
    STATUS_LATE,
    STATUS_NO_BEFORE_DEADLINE,
    STATUS_NO_AFTER_DEADLINE,
)
from bot.utils.markdown import escape_markdown_v2, bold
from bot.keyboards.gradebook import (
    kb_progress_filters,
    kb_training_select,
    kb_pagination,
    kb_filters_with_pagination,
    kb_training_select_with_status,
    kb_lesson_select_with_status,
)


def _format_counts(counts: dict) -> str:
    v_on = counts.get(STATUS_ON_TIME, 0)
    v_late = counts.get(STATUS_LATE, 0)
    v_nb = counts.get(STATUS_NO_BEFORE_DEADLINE, 0)
    v_na = counts.get(STATUS_NO_AFTER_DEADLINE, 0)
    lines = [
        escape_markdown_v2(f"✅ Сдали вовремя: {v_on}"),
        escape_markdown_v2(f"⏰ Сдали с опозданием: {v_late}"),
        escape_markdown_v2(f"⌛ Не сдали (дедлайн не прошёл): {v_nb}"),
        escape_markdown_v2(f"❌ Не сдали (дедлайн прошёл): {v_na}"),
    ]
    return "\n".join(lines)


async def cmd_progress(message: types.Message, config):
    user_id = message.from_user.id
    # Наставник — не админ
    if user_id in config.admin_ids:
        await message.answer("Вы выбрали команду для Наставника. Для просмотра табеля успеваемости, для вашей роли, используйте команду /progress_admin")
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
        await message.answer("Вы выбрали команду для Администратора. Для просмотра табеля успеваемости, для вашей роли, используйте команду /progress")
        return

    async for session in get_session():
        await _render_admin_list(message, session, training_id=None, lesson_id=None, page=1)


def _kb_progress_filters_with_tr(training_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Сменить тренинг", callback_data="gb:filter:training"),
        InlineKeyboardButton("Фильтр: урок", callback_data=f"gb:filter:lesson:tr:{training_id}"),
    )
    kb.add(
        InlineKeyboardButton("Статус: вовремя", callback_data=f"gb:status:on_time:tr:{training_id}"),
        InlineKeyboardButton("Статус: не вовремя", callback_data=f"gb:status:not_on_time:tr:{training_id}"),
    )
    kb.add(InlineKeyboardButton("Сбросить фильтры", callback_data="gb:back"))
    return kb


def _kb_lesson_select(options: list[tuple[int, str]], training_id: int, has_more: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    for lesson_id, title in options:
        title_short = title if len(title) <= 48 else title[:45] + "…"
        kb.add(InlineKeyboardButton(f"📗 {title_short}", callback_data=f"gb:set:lesson:{lesson_id}:tr:{training_id}"))
    if has_more:
        kb.add(InlineKeyboardButton("Показаны первые 10", callback_data="gb:nop"))
    kb.add(InlineKeyboardButton("← Назад", callback_data="gb:back"))
    return kb


def _format_summary_text(total: int, counts: dict, header: str) -> str:
    counts_text = _format_counts(counts)
    total_line = escape_markdown_v2(f"Всего студентов: {total}")
    return f"{header}\n\n{total_line}\n\n{counts_text}"


async def cb_progress_router(call: CallbackQuery, config):
    user_id = call.from_user.id
    data = call.data or ""
    if user_id in config.admin_ids:
        await call.answer()
        return

    async for session in get_session():
        from sqlalchemy import select
        from bot.services.database import Mentor, Mapping, Training, Lesson

        res = await session.execute(select(Mentor).where(Mentor.telegram_id == user_id))
        mentor = res.scalars().first()
        if not mentor:
            await call.answer("Нет доступа", show_alert=True)
            return

        # Фильтр: выбор тренинга
        if data == "gb:filter:training":
            q = await session.execute(select(Mapping.training_id).where(Mapping.mentor_id == mentor.id))
            training_ids = sorted({row[0] for row in q.fetchall()})
            if not training_ids:
                await call.answer("Нет тренингов", show_alert=True)
                return
            tr_res = await session.execute(select(Training).where(Training.id.in_(training_ids)))
            trainings = tr_res.scalars().all()
            # добавляем статус тренинга и запрещаем not_started
            options = []
            from bot.services.gradebook_service import get_training_state
            for t in trainings:
                lessons_res = await session.execute(select(Lesson).where(Lesson.training_id == t.id))
                lessons = lessons_res.scalars().all()
                state = get_training_state(lessons)
                state_emoji = {"active": "🟡", "completed": "🟢", "not_started": "🔴"}[state]
                allowed = state != "not_started"
                options.append((t.id, f"{state_emoji} {t.title or f'Training {t.id}'}", allowed))
            options = options[:10]
            await call.message.edit_reply_markup(reply_markup=kb_training_select_with_status(options, has_more=len(trainings) > 10))
            await call.answer()
            return

        # Показ списка студентов (детализация): gb:list:students [опц. фильтры + пагинация]
        if data.startswith("gb:list:students") or data.startswith("gb:page:students"):
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

            summary = await build_mentor_overview(session, mentor_id=mentor.id, training_id=training_id, lesson_id=lesson_id)

            # Счётчики по студентам: подсчёт статусов по items
            per_student = {}
            for it in summary.get("items", []):
                sid = it.get("student_id") if isinstance(it, dict) else it.student_id
                st = it.get("status") if isinstance(it, dict) else it.status
                if sid not in per_student:
                    per_student[sid] = {
                        STATUS_ON_TIME: 0,
                        STATUS_LATE: 0,
                        STATUS_NO_BEFORE_DEADLINE: 0,
                        STATUS_NO_AFTER_DEADLINE: 0,
                    }
                per_student[sid][st] += 1

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

            lines = ["📊 " + bold("Детализация студентов")]
            for sid in page_ids:
                info = students.get(sid, {})
                last = info.get("last_name") or ""
                first = info.get("first_name") or ""
                counters = per_student[sid]
                line = f"Студент: {last} {first}\n✅ - {counters[STATUS_ON_TIME]}📝 | ⏰ - {counters[STATUS_LATE]}📝 | ⌛ - {counters[STATUS_NO_BEFORE_DEADLINE]}📝 | ❌ - {counters[STATUS_NO_AFTER_DEADLINE]}📝"
                lines.append(escape_markdown_v2(line))

            text = "\n\n".join(lines)

            # Построение базового префикса для пагинации
            base = "gb:page:students"
            if training_id is not None:
                base += f":tr:{training_id}"
            if lesson_id is not None:
                base += f":lesson:{lesson_id}"

            await call.message.edit_text(text)
            await call.message.edit_reply_markup(reply_markup=kb_pagination(page, total_pages, base))
            await call.answer()
            return

        # Установка тренинга: gb:set:tr:{id}
        if data.startswith("gb:set:tr:"):
            try:
                training_id = int(data.split(":")[3])
            except Exception:
                await call.answer("Некорректный тренинг", show_alert=True)
                return
            await _render_students_list(call.message, session, mentor_id=mentor.id, training_id=training_id, lesson_id=None, page=1)
            await call.answer()
            return

        # Выбор урока: gb:filter:lesson:tr:{id}
        if data.startswith("gb:filter:lesson"):
            parts = data.split(":")
            # Проверяем формат: gb:filter:lesson или gb:filter:lesson:tr:ID
            if len(parts) < 3:
                await call.answer("Сначала выберите тренинг", show_alert=True)
                return

            training_id = None
            if len(parts) >= 5 and parts[3] == "tr":
                try:
                    training_id = int(parts[4])
                except Exception:
                    await call.answer("Некорректный тренинг", show_alert=True)
                    return
            else:
                await call.answer("Сначала выберите тренинг", show_alert=True)
                return

            try:
                lessons_res = await session.execute(select(Lesson).where(Lesson.training_id == training_id))
                lessons = lessons_res.scalars().all()
                if not lessons:
                    await call.answer("Нет уроков в данном тренинге", show_alert=True)
                    return

                from bot.services.gradebook_service import get_lesson_state
                opts = []
                for l in lessons:
                    state = get_lesson_state(l)
                    state_emoji = {"active": "🟡", "completed": "🟢", "not_started": "🔴"}[state]
                    allowed = state != "not_started"
                    # Добавляем номер урока, если есть
                    lesson_num = f"№{l.lesson_number}" if l.lesson_number is not None else ""
                    opts.append((l.id, f"{state_emoji} {lesson_num} {l.title or f'Lesson {l.id}'}", allowed))
                opts = opts[:10]
                await call.message.edit_reply_markup(reply_markup=kb_lesson_select_with_status(opts, training_id, has_more=len(lessons) > 10))
                await call.answer()
            except Exception as e:
                logger.error(f"Ошибка при выборе урока: {e}")
                await call.answer("Произошла ошибка при загрузке уроков", show_alert=True)
            return

        # Установка урока: gb:set:lesson:{lesson_id}:tr:{training_id}
        if data.startswith("gb:set:lesson:"):
            parts = data.split(":")
            # Проверяем формат: gb:set:lesson:LESSON_ID:tr:TRAINING_ID
            if len(parts) < 6 or parts[3] != "tr":
                await call.answer("Некорректные данные", show_alert=True)
                return

            try:
                lesson_id = int(parts[2])
                training_id = int(parts[4])
            except Exception:
                await call.answer("Некорректные данные", show_alert=True)
                return
            await _render_students_list(call.message, session, mentor_id=mentor.id, training_id=training_id, lesson_id=lesson_id, page=1)
            await call.answer()
            return

        # Блокировка выбора not_started
        if data == "gb:block:not_started":
            await call.answer("Статистика доступна только по активным и завершенным тренингам/урокам", show_alert=True)
            return

        if data == "gb:back":
            # Сброс к базовому экрану
            await _render_students_list(call.message, session, mentor_id=mentor.id, training_id=None, lesson_id=None, page=1)
            await call.answer()
            return

        if data == "gb:nop":
            await call.answer()
            return


def register_gradebook_handlers(dp: Dispatcher, config):
    dp.register_message_handler(lambda msg: cmd_progress(msg, config), commands=["progress"], state="*")
    dp.register_message_handler(lambda msg: cmd_progress_admin(msg, config), commands=["progress_admin"], state="*")
    dp.register_callback_query_handler(lambda c: cb_progress_router(c, config), lambda c: c.data and c.data.startswith("gb:"), state="*")


from typing import Optional


async def _render_students_list(message: types.Message, session, mentor_id: int, training_id: Optional[int], lesson_id: Optional[int], page: int):
    from bot.services.gradebook_service import build_mentor_overview
    summary = await build_mentor_overview(session, mentor_id=mentor_id, training_id=training_id, lesson_id=lesson_id, include_not_started=False)

    # counters per student
    per_student = {}
    for it in summary.get("items", []):
        sid = it.get("student_id") if isinstance(it, dict) else it.student_id
        st = it.get("status") if isinstance(it, dict) else it.status
        per_student.setdefault(sid, {
            STATUS_ON_TIME: 0,
            STATUS_LATE: 0,
            STATUS_NO_BEFORE_DEADLINE: 0,
            STATUS_NO_AFTER_DEADLINE: 0,
        })[st] += 1

    # order students
    students = summary.get("students", {})
    def sort_key(sid):
        info = students.get(sid, {})
        last = (info.get("last_name") or "").lower()
        first = (info.get("first_name") or "").lower()
        return (last, first, sid)
    ordered_ids = sorted(per_student.keys(), key=sort_key)

    # paging
    page_size = 20
    total_pages = max(1, (len(ordered_ids) + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    page_ids = ordered_ids[start:end]

    # header with filters
    if training_id is None:
        tr_line = "Тренинг: по всем активным и завершенным тренингам"
    else:
        from sqlalchemy import select
        from bot.services.database import Training
        tr = await session.execute(select(Training).where(Training.id == training_id))
        t = tr.scalars().first()
        tr_line = f"Тренинг: {t.title if t and t.title else training_id}"
    if lesson_id is None:
        ls_line = "Урок: по всем активным и завершенным урокам"
    else:
        from sqlalchemy import select
        from bot.services.database import Lesson
        lr = await session.execute(select(Lesson).where(Lesson.id == lesson_id))
        l = lr.scalars().first()
        ls_line = f"Урок: {l.title if l and l.title else lesson_id}"

    lines = [
        "📊 " + bold("Статистика ваших студентов"),
        escape_markdown_v2(tr_line),
        escape_markdown_v2(ls_line),
        "",
        escape_markdown_v2("✅ Ответ на урок предоставлен до его завершения"),
        escape_markdown_v2("⏰ Ответ на урок предоставлен после его завершения"),
        escape_markdown_v2("⌛ Нет ответа на активный урок"),
        escape_markdown_v2("❌ Нет ответа на завершенный урок"),
        escape_markdown_v2("📝 Число уроков в каждом статусе"),
        "",
    ]
    for sid in page_ids:
        info = students.get(sid, {})
        last = info.get("last_name") or ""
        first = info.get("first_name") or ""
        counters = per_student[sid]
        lines.append(escape_markdown_v2(f"Студент: {last} {first}"))
        lines.append(escape_markdown_v2(f"✅ - {counters[STATUS_ON_TIME]}📝 | ⏰ - {counters[STATUS_LATE]}📝 | ⌛ - {counters[STATUS_NO_BEFORE_DEADLINE]}📝 | ❌ - {counters[STATUS_NO_AFTER_DEADLINE]}📝"))

    text = "\n".join(lines)
    base = "gb:page:students"
    if training_id is not None:
        base += f":tr:{training_id}"
    if lesson_id is not None:
        base += f":lesson:{lesson_id}"
    await message.answer(text, reply_markup=kb_filters_with_pagination(training_id, lesson_id, page, total_pages, base))


async def _render_admin_list(message: types.Message, session, training_id: Optional[int], lesson_id: Optional[int], page: int):
    from sqlalchemy import select
    from bot.services.database import Mentor
    mentors_res = await session.execute(select(Mentor))
    mentors = mentors_res.scalars().all()

    blocks = []  # [(mentor_display, [(student_display, counters_dict), ...])]
    from bot.services.gradebook_service import build_mentor_overview
    for m in mentors:
        summary = await build_mentor_overview(session, mentor_id=m.id, training_id=training_id, lesson_id=lesson_id, include_not_started=False)
        students = summary.get("students", {})
        per_student = {}
        for it in summary.get("items", []):
            sid = it.get("student_id") if isinstance(it, dict) else it.student_id
            st = it.get("status") if isinstance(it, dict) else it.status
            per_student.setdefault(sid, {
                STATUS_ON_TIME: 0,
                STATUS_LATE: 0,
                STATUS_NO_BEFORE_DEADLINE: 0,
                STATUS_NO_AFTER_DEADLINE: 0,
            })[st] += 1
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
            student_rows.append((f"Студент: {last} {first}", f"✅ - {counters[STATUS_ON_TIME]}📝 | ⏰ - {counters[STATUS_LATE]}📝 | ⌛ - {counters[STATUS_NO_BEFORE_DEADLINE]}📝 | ❌ - {counters[STATUS_NO_AFTER_DEADLINE]}📝"))
        mentor_name = f"Наставник: {m.last_name or ''} {m.first_name or ''}".strip()
        blocks.append((mentor_name, student_rows, len(student_rows) if student_rows else 1))

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

    # header with filters
    if training_id is None:
        tr_line = "Тренинг: по всем тренингам"
    else:
        from bot.services.database import Training
        tr = await session.execute(select(Training).where(Training.id == training_id))
        t = tr.scalars().first()
        tr_line = f"Тренинг: {t.title if t and t.title else training_id}"
    if lesson_id is None:
        ls_line = "Урок: по всем  урокам"
    else:
        from bot.services.database import Lesson
        lr = await session.execute(select(Lesson).where(Lesson.id == lesson_id))
        l = lr.scalars().first()
        ls_line = f"Урок: {l.title if l and l.title else lesson_id}"

    lines = [
        "📈 " + bold("Статистика по наставникам"),
        escape_markdown_v2(tr_line),
        escape_markdown_v2(ls_line),
        "",
        escape_markdown_v2("✅ Ответ на урок предоставлен до его завершения"),
        escape_markdown_v2("⏰ Ответ на урок предоставлен после его завершения"),
        escape_markdown_v2("⌛ Нет ответа на активный урок"),
        escape_markdown_v2("❌ Нет ответа на завершенный урок"),
        escape_markdown_v2("📝 Число уроков в каждом статусе"),
        "",
    ]
    for mentor_name, rows in page_blocks:
        lines.append(escape_markdown_v2(mentor_name))
        for title, counters in rows:
            lines.append(escape_markdown_v2(title))
            lines.append(escape_markdown_v2(counters))

    text = "\n".join(lines)
    base = "gb:page:admin"
    if training_id is not None:
        base += f":tr:{training_id}"
    if lesson_id is not None:
        base += f":lesson:{lesson_id}"
    await message.answer(text, reply_markup=kb_filters_with_pagination(training_id, lesson_id, page, total_pages, base))
