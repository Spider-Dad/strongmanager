import os
import asyncio
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from bot.services.database import (
    Mentor, Student, Mapping, Training, Lesson, Log, Notification, WebhookRawLog, DebugLog, Base
)
from bot.services import database
from sqlalchemy import text

# === НАСТРОЙКИ ===
CREDENTIALS_FILE = 'central-insight-409215-196210033b14.json'
SPREADSHEET_ID = '1HAq1DHBQH0xLthA-gvnBOg-0vpkDjaBsEOQxNx51WLo'
DB_PATH = 'getcourse_bot/data/database/getcourse_bot.db'  # путь БД

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# --- ЯВНАЯ ИНИЦИАЛИЗАЦИЯ async_engine ---
database.async_engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False)
async_engine = database.async_engine
# ----------------------------------------

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
def parse_date(val):
    if not val:
        return None
    try:
        # Google Sheets может возвращать дату как строку или datetime
        if isinstance(val, datetime):
            return val
        # Попробуем разные форматы
        for fmt in ("%d.%m.%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(val, fmt)
            except Exception:
                continue
        return None
    except Exception:
        return None

def get_int(val):
    try:
        return int(val)
    except Exception:
        return None

# === ОСНОВНОЙ СКРИПТ ===
async def import_data():
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)

    # Чтение всех листов
    mentors_data = sh.worksheet('mentors').get_all_records()
    students_data = sh.worksheet('students').get_all_records()
    mapping_data = sh.worksheet('mapping').get_all_records()
    trainings_data = sh.worksheet('trainings').get_all_records()
    lessons_data = sh.worksheet('lessons').get_all_records()
    logs_data = sh.worksheet('logs').get_all_records()
    notifications_data = sh.worksheet('notifications').get_all_records()
    webhook_raw_log_data = sh.worksheet('webhook_raw_log').get_all_records()
    debug_log_data = sh.worksheet('debug_log').get_all_records()

    # Создание таблиц
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        # ОЧИСТКА ВСЕХ ТАБЛИЦ ПЕРЕД ИМПОРТОМ
        await session.execute(text('DELETE FROM mentors'))
        await session.execute(text('DELETE FROM students'))
        await session.execute(text('DELETE FROM mapping'))
        await session.execute(text('DELETE FROM trainings'))
        await session.execute(text('DELETE FROM lessons'))
        await session.execute(text('DELETE FROM logs'))
        await session.execute(text('DELETE FROM notifications'))
        await session.execute(text('DELETE FROM webhook_raw_log'))
        await session.execute(text('DELETE FROM debug_log'))
        await session.commit()
        # mentors
        for row in mentors_data:
            mentor = Mentor(
                id=get_int(row.get('mentorId') or row.get('id')),
                email=row.get('email'),
                first_name=row.get('firstName'),
                last_name=row.get('lastName'),
                telegram_id=get_int(row.get('telegramId')),
                username=row.get('telegramUsername')
            )
            session.add(mentor)
        # students
        for row in students_data:
            student = Student(
                id=get_int(row.get('studentId') or row.get('id')),
                user_email=row.get('userEmail'),
                first_name=row.get('userFirstName'),
                last_name=row.get('userLastName')
            )
            session.add(student)
        # mapping
        for row in mapping_data:
            mapping = Mapping(
                id=get_int(row.get('id')),
                student_id=get_int(row.get('studentId')),
                mentor_id=get_int(row.get('mentorId')),
                training_id=get_int(row.get('trainingId')),
                assigned_date=parse_date(row.get('assignedDate'))
            )
            session.add(mapping)
        # trainings
        for row in trainings_data:
            training = Training(
                id=get_int(row.get('trainingId') or row.get('id')),
                title=row.get('trainingTitle') or row.get('title'),
                is_active=True,
                progress_table_id=row.get('progressTableId')
            )
            session.add(training)
        # lessons
        for row in lessons_data:
            lesson = Lesson(
                id=get_int(row.get('lessonId') or row.get('id')),
                training_id=get_int(row.get('trainingId')),
                module_number=get_int(row.get('moduleNumber')),
                lesson_number=get_int(row.get('lessonNumber')),
                title=row.get('lessonTitle') or row.get('title'),
                opening_date=parse_date(row.get('openingDate')),
                deadline_date=parse_date(row.get('deadlineDate'))
            )
            session.add(lesson)
        # logs
        for row in logs_data:
            log = Log(
                date=parse_date(row.get('date')),
                user_id=get_int(row.get('userId')),
                user_email=row.get('userEmail'),
                user_first_name=row.get('userFirstName'),
                user_last_name=row.get('userLastName'),
                answer_id=row.get('answerId'),
                answer_training_id=get_int(row.get('answerTrainingId')),
                answer_lesson_id=get_int(row.get('answerLessonId')),
                answer_status=row.get('answerStatus'),
                answer_text=row.get('answerText'),
                answer_type=row.get('answerType'),
                answer_teacher_id=row.get('answerTeacherId'),
                answer_training_title=row.get('answerTrainingTitle'),
                action=row.get('action'),
                webhook_date=parse_date(row.get('webhookDate'))
            )
            session.add(log)
        # notifications
        for row in notifications_data:
            notification = Notification(
                mentor_id=get_int(row.get('ID получателя') or row.get('mentor_id')),
                type=row.get('Тип уведомления') or row.get('type'),
                message=row.get('Сообщение') or row.get('message'),
                status=row.get('Статус') or row.get('status'),
                created_at=parse_date(row.get('Дата') or row.get('created_at')),
                sent_at=parse_date(row.get('sent_at')),
                telegram_message_id=str(row.get('TelegramMessageId') or row.get('telegram_message_id'))
            )
            session.add(notification)
        # webhook_raw_log
        for row in webhook_raw_log_data:
            webhook = WebhookRawLog(
                date=parse_date(row.get('Дата') or row.get('date')),
                raw_data=row.get('RawData') or row.get('raw_data')
            )
            session.add(webhook)
        # debug_log
        for row in debug_log_data:
            debug = DebugLog(
                date=parse_date(row.get('Дата') or row.get('date')),
                event=row.get('Событие') or row.get('event'),
                data=row.get('Данные') or row.get('data')
            )
            session.add(debug)
        await session.commit()
    print('Импорт завершён успешно!')

if __name__ == "__main__":
    asyncio.run(import_data())