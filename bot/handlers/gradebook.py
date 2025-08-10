from aiogram import types
from aiogram.dispatcher import Dispatcher
from aiogram.types import CallbackQuery

from bot.services.database import get_session
from bot.services.gradebook_service import (
    build_mentor_overview,
    build_admin_overview,
    STATUS_ON_TIME,
    STATUS_LATE,
    STATUS_NO_BEFORE_DEADLINE,
    STATUS_NO_AFTER_DEADLINE,
)
from bot.utils.markdown import escape_markdown_v2, bold
from bot.keyboards.gradebook import kb_progress_filters, kb_training_select
from bot.keyboards.gradebook import InlineKeyboardMarkup, InlineKeyboardButton  # reuse types


def _format_counts(counts: dict) -> str:
    v_on = counts.get(STATUS_ON_TIME, 0)
    v_late = counts.get(STATUS_LATE, 0)
    v_nb = counts.get(STATUS_NO_BEFORE_DEADLINE, 0)
    v_na = counts.get(STATUS_NO_AFTER_DEADLINE, 0)
    return (
        f"✅ Сдали вовремя: {v_on}\n"
        f"⏰ Сдали с опозданием: {v_late}\n"
        f"⌛ Не сдали (дедлайн не прошёл): {v_nb}\n"
        f"❌ Не сдали (дедлайн прошёл): {v_na}"
    )


async def cmd_progress(message: types.Message, config):
    user_id = message.from_user.id
    # Наставник — не админ
    if user_id in config.admin_ids:
        await message.answer("Команда доступна только наставникам. Используйте /progress_admin.")
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

        summary = await build_mentor_overview(session, mentor_id=mentor.id)
        counts_text = _format_counts(summary.get("counts", {}))
        total = summary.get("total_students", 0)
        text = f"📊 {bold('Прогресс ваших студентов')}\n\nВсего студентов: {total}\n\n{counts_text}"
        await message.answer(text, reply_markup=kb_progress_filters())


async def cmd_progress_admin(message: types.Message, config):
    user_id = message.from_user.id
    if user_id not in config.admin_ids:
        await message.answer("Доступ запрещён.")
        return

    async for session in get_session():
        summary = await build_admin_overview(session)
        mentors = summary.get("mentors", {})
        lines = ["📈 " + bold("Сводка по наставникам")]
        for mid, data in mentors.items():
            counts = data.get("counts", {})
            total = data.get("total_students", 0)
            not_on_time = counts.get(STATUS_LATE, 0) + counts.get(STATUS_NO_BEFORE_DEADLINE, 0) + counts.get(STATUS_NO_AFTER_DEADLINE, 0)
            perc = f"{int(not_on_time / max(total, 1) * 100)}%" if total else "0%"
            lines.append(f"Наставник {mid}: не вовремя {not_on_time} ({perc})")
        await message.answer("\n".join(lines))


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
    return f"{header}\n\nВсего студентов: {total}\n\n{counts_text}"


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
            options = [(t.id, t.title or f"Training {t.id}") for t in trainings][:10]
            await call.message.edit_reply_markup(reply_markup=kb_training_select(options, has_more=len(trainings) > 10))
            await call.answer()
            return

        # Установка тренинга: gb:set:tr:{id}
        if data.startswith("gb:set:tr:"):
            try:
                training_id = int(data.split(":")[3])
            except Exception:
                await call.answer("Некорректный тренинг", show_alert=True)
                return
            summary = await build_mentor_overview(session, mentor_id=mentor.id, training_id=training_id)
            text = _format_summary_text(summary.get("total_students", 0), summary.get("counts", {}), "📊 " + bold("Прогресс (фильтр: тренинг)"))
            await call.message.edit_text(text)
            await call.message.edit_reply_markup(reply_markup=_kb_progress_filters_with_tr(training_id))
            await call.answer()
            return

        # Выбор урока: gb:filter:lesson:tr:{id}
        if data.startswith("gb:filter:lesson"):
            parts = data.split(":")
            if len(parts) < 4 or parts[2] != "tr":
                await call.answer("Сначала выберите тренинг", show_alert=True)
                return
            try:
                training_id = int(parts[3])
            except Exception:
                await call.answer("Некорректный тренинг", show_alert=True)
                return
            lessons_res = await session.execute(select(Lesson).where(Lesson.training_id == training_id))
            lessons = lessons_res.scalars().all()
            options = [(l.id, l.title or f"Lesson {l.id}") for l in lessons][:10]
            await call.message.edit_reply_markup(reply_markup=_kb_lesson_select(options, training_id, has_more=len(lessons) > 10))
            await call.answer()
            return

        # Установка урока: gb:set:lesson:{lesson_id}:tr:{training_id}
        if data.startswith("gb:set:lesson:"):
            parts = data.split(":")
            try:
                lesson_id = int(parts[2])
                training_id = int(parts[4]) if len(parts) > 4 and parts[3] == "tr" else None
            except Exception:
                await call.answer("Некорректные данные", show_alert=True)
                return
            summary = await build_mentor_overview(session, mentor_id=mentor.id, training_id=training_id, lesson_id=lesson_id)
            text = _format_summary_text(summary.get("total_students", 0), summary.get("counts", {}), "📊 " + bold("Прогресс (фильтр: урок)"))
            kb = _kb_progress_filters_with_tr(training_id) if training_id else kb_progress_filters()
            await call.message.edit_text(text)
            await call.message.edit_reply_markup(reply_markup=kb)
            await call.answer()
            return

        # Фильтр по статусу: on_time / not_on_time, с опциональным tr/lesson
        if data.startswith("gb:status:"):
            parts = data.split(":")
            status_key = parts[2]
            training_id = None
            lesson_id = None
            # поиск опциональных параметров
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

            summary = await build_mentor_overview(session, mentor_id=mentor.id, training_id=training_id, lesson_id=lesson_id)

            # Пересчитываем counts с учётом фильтра статусов
            items = summary.get("items", [])
            if status_key == "on_time":
                allowed = {STATUS_ON_TIME}
            else:
                allowed = {STATUS_LATE, STATUS_NO_BEFORE_DEADLINE, STATUS_NO_AFTER_DEADLINE}
            filtered_counts = {
                STATUS_ON_TIME: 0,
                STATUS_LATE: 0,
                STATUS_NO_BEFORE_DEADLINE: 0,
                STATUS_NO_AFTER_DEADLINE: 0,
            }
            for it in items:
                st = it.get("status") if isinstance(it, dict) else it.status
                if st in allowed:
                    filtered_counts[st] += 1

            header = "📊 " + bold("Прогресс (фильтр: статус)")
            text = _format_summary_text(summary.get("total_students", 0), filtered_counts, header)
            kb = _kb_progress_filters_with_tr(training_id) if training_id else kb_progress_filters()
            await call.message.edit_text(text)
            await call.message.edit_reply_markup(reply_markup=kb)
            await call.answer()
            return

        if data == "gb:back":
            # Сброс к базовому экрану
            summary = await build_mentor_overview(session, mentor_id=mentor.id)
            text = _format_summary_text(summary.get("total_students", 0), summary.get("counts", {}), "📊 " + bold("Прогресс ваших студентов"))
            await call.message.edit_text(text)
            await call.message.edit_reply_markup(reply_markup=kb_progress_filters())
            await call.answer()
            return

        if data == "gb:nop":
            await call.answer()
            return


def register_gradebook_handlers(dp: Dispatcher, config):
    dp.register_message_handler(lambda msg: cmd_progress(msg, config), commands=["progress"], state="*")
    dp.register_message_handler(lambda msg: cmd_progress_admin(msg, config), commands=["progress_admin"], state="*")
    dp.register_callback_query_handler(lambda c: cb_progress_router(c, config), lambda c: c.data and c.data.startswith("gb:"), state="*")
