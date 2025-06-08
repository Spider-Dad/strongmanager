import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, Column, DateTime, String, Integer
from bot.services.database import Base
from bot.services import database
import json

logger = logging.getLogger(__name__)

# Модель для хранения информации о синхронизациях
class SyncHistory(Base):
    __tablename__ = "sync_history"

    id = Column(Integer, primary_key=True)
    sync_date = Column(DateTime, nullable=False)
    status = Column(String(20), nullable=False)  # success, failed
    duration_seconds = Column(Integer, nullable=True)
    error_message = Column(String(500), nullable=True)
    records_synced = Column(String(500), nullable=True)  # JSON с количеством записей по таблицам

class SyncService:
    def __init__(self, config):
        self.config = config
        self.credentials_file = config.google_credentials_path
        self.spreadsheet_id = config.google_spreadsheet_id
        self.scopes = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        self.is_syncing = False
        self.last_sync_info = None
        self.sync_task = None

        # Получаем интервал синхронизации из переменной окружения (в минутах)
        self.sync_interval = int(os.getenv("SYNC_INTERVAL_MINUTES", "0"))

    async def start_auto_sync(self):
        """Запускает автоматическую синхронизацию по расписанию"""
        if self.sync_interval <= 0:
            logger.info("Автоматическая синхронизация отключена (SYNC_INTERVAL_MINUTES=0)")
            return

        logger.info(f"Запуск автоматической синхронизации с интервалом {self.sync_interval} минут")
        self.sync_task = asyncio.create_task(self._auto_sync_loop())

    async def stop_auto_sync(self):
        """Останавливает автоматическую синхронизацию"""
        if self.sync_task:
            self.sync_task.cancel()
            try:
                await self.sync_task
            except asyncio.CancelledError:
                pass
            self.sync_task = None

    async def _auto_sync_loop(self):
        """Цикл автоматической синхронизации"""
        while True:
            try:
                await self.sync_database()
                await asyncio.sleep(self.sync_interval * 60)  # Конвертируем минуты в секунды
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле автоматической синхронизации: {e}", exc_info=True)
                await asyncio.sleep(60)  # Подождем минуту перед повторной попыткой

    def parse_date(self, val):
        """Парсинг даты из различных форматов"""
        if not val:
            return None
        try:
            if isinstance(val, datetime):
                return val
            for fmt in ("%d.%m.%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(val, fmt)
                except Exception:
                    continue
            return None
        except Exception:
            return None

    def get_int(self, val):
        """Безопасное преобразование в int"""
        try:
            return int(val)
        except Exception:
            return None

    async def sync_database(self) -> Dict[str, Any]:
        """Выполняет синхронизацию БД с Google Sheets"""
        if self.is_syncing:
            return {"success": False, "error": "Синхронизация уже выполняется"}

        self.is_syncing = True
        start_time = datetime.now()
        sync_result = {
            "success": False,
            "start_time": start_time,
            "duration": 0,
            "records_synced": {},
            "error": None
        }

        try:
            # Авторизация в Google Sheets
            creds = Credentials.from_service_account_file(self.credentials_file, scopes=self.scopes)
            gc = gspread.authorize(creds)
            sh = gc.open_by_key(self.spreadsheet_id)

            # Чтение всех листов
            logger.info("Начало чтения данных из Google Sheets")
            sheets_data = {
                'mentors': sh.worksheet('mentors').get_all_records(),
                'students': sh.worksheet('students').get_all_records(),
                'mapping': sh.worksheet('mapping').get_all_records(),
                'trainings': sh.worksheet('trainings').get_all_records(),
                'lessons': sh.worksheet('lessons').get_all_records(),
                'logs': sh.worksheet('logs').get_all_records(),
                'notifications': sh.worksheet('notifications').get_all_records(),
                'webhook_raw_log': sh.worksheet('webhook_raw_log').get_all_records(),
                'debug_log': sh.worksheet('debug_log').get_all_records()
            }

            # Импорт данных в БД
            async with database.async_session() as session:
                # Очистка таблиц
                logger.info("Очистка таблиц перед импортом")
                for table_name in sheets_data.keys():
                    await session.execute(text(f'DELETE FROM {table_name}'))
                await session.commit()

                # Импорт данных по таблицам
                from bot.services.database import (
                    Mentor, Student, Mapping, Training, Lesson,
                    Log, Notification, WebhookRawLog, DebugLog
                )

                # Mentors
                for row in sheets_data['mentors']:
                    mentor = Mentor(
                        id=self.get_int(row.get('mentorId') or row.get('id')),
                        email=row.get('email'),
                        first_name=row.get('firstName'),
                        last_name=row.get('lastName'),
                        telegram_id=self.get_int(row.get('telegramId')),
                        username=row.get('telegramUsername')
                    )
                    session.add(mentor)
                sync_result['records_synced']['mentors'] = len(sheets_data['mentors'])

                # Students
                for row in sheets_data['students']:
                    student = Student(
                        id=self.get_int(row.get('studentId') or row.get('id')),
                        user_email=row.get('userEmail'),
                        first_name=row.get('userFirstName'),
                        last_name=row.get('userLastName')
                    )
                    session.add(student)
                sync_result['records_synced']['students'] = len(sheets_data['students'])

                # Mapping
                for row in sheets_data['mapping']:
                    mapping = Mapping(
                        id=self.get_int(row.get('id')),
                        student_id=self.get_int(row.get('studentId')),
                        mentor_id=self.get_int(row.get('mentorId')),
                        training_id=self.get_int(row.get('trainingId')),
                        assigned_date=self.parse_date(row.get('assignedDate'))
                    )
                    session.add(mapping)
                sync_result['records_synced']['mapping'] = len(sheets_data['mapping'])

                # Trainings
                for row in sheets_data['trainings']:
                    training = Training(
                        id=self.get_int(row.get('trainingId') or row.get('id')),
                        title=row.get('trainingTitle') or row.get('title'),
                        is_active=True,
                        progress_table_id=row.get('progressTableId')
                    )
                    session.add(training)
                sync_result['records_synced']['trainings'] = len(sheets_data['trainings'])

                # Lessons
                for row in sheets_data['lessons']:
                    lesson = Lesson(
                        id=self.get_int(row.get('lessonId') or row.get('id')),
                        training_id=self.get_int(row.get('trainingId')),
                        module_number=self.get_int(row.get('moduleNumber')),
                        lesson_number=self.get_int(row.get('lessonNumber')),
                        title=row.get('lessonTitle') or row.get('title'),
                        opening_date=self.parse_date(row.get('openingDate')),
                        deadline_date=self.parse_date(row.get('deadlineDate'))
                    )
                    session.add(lesson)
                sync_result['records_synced']['lessons'] = len(sheets_data['lessons'])

                # Logs
                for row in sheets_data['logs']:
                    log = Log(
                        date=self.parse_date(row.get('date')),
                        user_id=self.get_int(row.get('userId')),
                        user_email=row.get('userEmail'),
                        user_first_name=row.get('userFirstName'),
                        user_last_name=row.get('userLastName'),
                        answer_id=row.get('answerId'),
                        answer_training_id=self.get_int(row.get('answerTrainingId')),
                        answer_lesson_id=self.get_int(row.get('answerLessonId')),
                        answer_status=row.get('answerStatus'),
                        answer_text=row.get('answerText'),
                        answer_type=row.get('answerType'),
                        answer_teacher_id=row.get('answerTeacherId'),
                        answer_training_title=row.get('answerTrainingTitle'),
                        action=row.get('action'),
                        webhook_date=self.parse_date(row.get('webhookDate'))
                    )
                    session.add(log)
                sync_result['records_synced']['logs'] = len(sheets_data['logs'])

                # Notifications
                for row in sheets_data['notifications']:
                    notification = Notification(
                        mentor_id=self.get_int(row.get('ID получателя') or row.get('mentor_id')),
                        type=row.get('Тип уведомления') or row.get('type'),
                        message=row.get('Сообщение') or row.get('message'),
                        status=row.get('Статус') or row.get('status'),
                        created_at=self.parse_date(row.get('Дата') or row.get('created_at')),
                        sent_at=self.parse_date(row.get('sent_at')),
                        telegram_message_id=str(row.get('TelegramMessageId') or row.get('telegram_message_id'))
                    )
                    session.add(notification)
                sync_result['records_synced']['notifications'] = len(sheets_data['notifications'])

                # WebhookRawLog
                for row in sheets_data['webhook_raw_log']:
                    webhook = WebhookRawLog(
                        date=self.parse_date(row.get('Дата') or row.get('date')),
                        raw_data=row.get('RawData') or row.get('raw_data')
                    )
                    session.add(webhook)
                sync_result['records_synced']['webhook_raw_log'] = len(sheets_data['webhook_raw_log'])

                # DebugLog
                for row in sheets_data['debug_log']:
                    debug = DebugLog(
                        date=self.parse_date(row.get('Дата') or row.get('date')),
                        event=row.get('Событие') or row.get('event'),
                        data=row.get('Данные') or row.get('data')
                    )
                    session.add(debug)
                sync_result['records_synced']['debug_log'] = len(sheets_data['debug_log'])

                await session.commit()

                # Сохраняем информацию о синхронизации
                end_time = datetime.now()
                duration = int((end_time - start_time).total_seconds())

                sync_history = SyncHistory(
                    sync_date=start_time,
                    status='success',
                    duration_seconds=duration,
                    records_synced=json.dumps(sync_result['records_synced'])
                )
                session.add(sync_history)
                await session.commit()

                sync_result['success'] = True
                sync_result['duration'] = duration
                sync_result['end_time'] = end_time

                logger.info(f"Синхронизация завершена успешно. Синхронизировано записей: {sync_result['records_synced']}")

        except Exception as e:
            error_msg = f"Ошибка синхронизации: {str(e)}"
            logger.error(error_msg, exc_info=True)
            sync_result['error'] = error_msg

            # Сохраняем информацию об ошибке
            try:
                async with database.async_session() as session:
                    sync_history = SyncHistory(
                        sync_date=start_time,
                        status='failed',
                        duration_seconds=int((datetime.now() - start_time).total_seconds()),
                        error_message=error_msg[:500]  # Ограничиваем длину сообщения об ошибке
                    )
                    session.add(sync_history)
                    await session.commit()
            except Exception as save_error:
                logger.error(f"Ошибка сохранения истории синхронизации: {save_error}")

        finally:
            self.is_syncing = False
            self.last_sync_info = sync_result

        return sync_result

    async def get_sync_status(self) -> Dict[str, Any]:
        """Получает информацию о последней синхронизации"""
        try:
            async with database.async_session() as session:
                # Получаем последнюю запись из истории
                result = await session.execute(
                    text("""
                        SELECT sync_date, status, duration_seconds, error_message, records_synced
                        FROM sync_history
                        ORDER BY sync_date DESC
                        LIMIT 1
                    """)
                )
                row = result.fetchone()

                if row:
                    records_synced = {}
                    try:
                        records_synced = json.loads(row[4]) if row[4] else {}
                    except:
                        pass

                    return {
                        "last_sync_date": row[0],
                        "status": row[1],
                        "duration_seconds": row[2],
                        "error_message": row[3],
                        "records_synced": records_synced,
                        "is_syncing": self.is_syncing,
                        "auto_sync_enabled": self.sync_interval > 0,
                        "sync_interval_minutes": self.sync_interval
                    }
                else:
                    return {
                        "last_sync_date": None,
                        "status": "never",
                        "is_syncing": self.is_syncing,
                        "auto_sync_enabled": self.sync_interval > 0,
                        "sync_interval_minutes": self.sync_interval
                    }
        except Exception as e:
            logger.error(f"Ошибка получения статуса синхронизации: {e}")
            return {
                "error": str(e),
                "is_syncing": self.is_syncing,
                "auto_sync_enabled": self.sync_interval > 0,
                "sync_interval_minutes": self.sync_interval
            }

    async def ensure_sync_table(self):
        """Создает таблицу истории синхронизации если её нет"""
        # Используем async_engine из модуля database, который уже должен быть инициализирован
        if database.async_engine is None:
            raise RuntimeError("Database engine not initialized. Call setup_database() first.")

        async with database.async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)