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


async def cb_progress_filters(call: CallbackQuery, config):
    user_id = call.from_user.id
    if user_id in config.admin_ids:
        await call.answer()
        return
    async for session in get_session():
        from sqlalchemy import select
        from bot.services.database import Mentor, Mapping, Training
        res = await session.execute(select(Mentor).where(Mentor.telegram_id == user_id))
        mentor = res.scalars().first()
        if not mentor:
            await call.answer("Нет доступа", show_alert=True)
            return
        # Список тренингов наставника
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


def register_gradebook_handlers(dp: Dispatcher, config):
    dp.register_message_handler(lambda msg: cmd_progress(msg, config), commands=["progress"], state="*")
    dp.register_message_handler(lambda msg: cmd_progress_admin(msg, config), commands=["progress_admin"], state="*")
    dp.register_callback_query_handler(lambda c: cb_progress_filters(c, config), text=["gb:filter:training", "gb:filter:lesson", "gb:status:on_time", "gb:status:not_on_time", "gb:back", "gb:nop"], state="*")
