import logging
from pathlib import Path

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)

# Базовый класс для моделей SQLAlchemy
Base = declarative_base()

# Модель для хранения данных о менторах
class Mentor(Base):
    __tablename__ = "mentors"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=True)
    email = Column(String(255), unique=True, nullable=False)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    username = Column(String(255), nullable=True)

# Модель для хранения истории уведомлений
class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    mentor_id = Column(Integer, nullable=False)
    type = Column(String(50), nullable=False)  # Тип уведомления: answerToLesson, commentOnLesson, etc.
    message = Column(Text, nullable=False)  # Сообщение уведомления
    status = Column(String(20), default="pending")  # pending, sent, failed
    created_at = Column(DateTime, server_default=func.now())
    sent_at = Column(DateTime, nullable=True)
    telegram_message_id = Column(String(50), nullable=True)  # ID апдейта Telegram

# Модель для хранения данных о студентах
class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True)
    user_email = Column(String(255), nullable=False)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)

# Модель для хранения данных о сопоставлении студентов и менторов
class Mapping(Base):
    __tablename__ = "mapping"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, nullable=False)
    mentor_id = Column(Integer, nullable=False)
    training_id = Column(Integer, nullable=False)
    assigned_date = Column(DateTime, nullable=True)

# Модель для хранения данных о тренировках
class Training(Base):
    __tablename__ = "trainings"
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    progress_table_id = Column(String(255), nullable=True)

# Модель для хранения данных о занятиях
class Lesson(Base):
    __tablename__ = "lessons"
    id = Column(Integer, primary_key=True)
    training_id = Column(Integer, nullable=False)
    module_number = Column(Integer, nullable=True)
    lesson_number = Column(Integer, nullable=True)
    title = Column(String(255), nullable=True)
    opening_date = Column(DateTime, nullable=True)
    deadline_date = Column(DateTime, nullable=True)

# Модель для хранения данных о логах
class Log(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, nullable=True)
    user_id = Column(Integer, nullable=True)
    user_email = Column(String(255), nullable=True)
    user_first_name = Column(String(255), nullable=True)
    user_last_name = Column(String(255), nullable=True)
    answer_id = Column(String(255), nullable=True)
    answer_training_id = Column(Integer, nullable=True)
    answer_lesson_id = Column(Integer, nullable=True)
    answer_status = Column(String(50), nullable=True)
    answer_text = Column(Text, nullable=True)
    answer_type = Column(String(50), nullable=True)
    answer_teacher_id = Column(String(255), nullable=True)
    answer_training_title = Column(String(255), nullable=True)
    action = Column(String(50), nullable=True)
    webhook_date = Column(DateTime, nullable=True)

# Модель для хранения данных о необработанных вебхуках
class WebhookRawLog(Base):
    __tablename__ = "webhook_raw_log"
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, nullable=True)
    raw_data = Column(Text, nullable=True)

# Модель для хранения данных о вебхуках отладки
class DebugLog(Base):
    __tablename__ = "debug_log"
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, nullable=True)
    event = Column(String(255), nullable=True)  # Название функции/события
    data = Column(Text, nullable=True)          # Данные события

# Модель для хранения логов приложения
class ApplicationLog(Base):
    __tablename__ = "application_logs"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, server_default=func.now())
    level = Column(String(20), nullable=False)  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    logger_name = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    module = Column(String(255), nullable=True)
    function = Column(String(255), nullable=True)
    line = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

# Модель для хранения ошибок приложения (для быстрого поиска)
class ErrorLog(Base):
    __tablename__ = "error_logs"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, server_default=func.now())
    level = Column(String(20), nullable=False)  # WARNING, ERROR, CRITICAL
    logger_name = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    traceback = Column(Text, nullable=True)
    module = Column(String(255), nullable=True)
    function = Column(String(255), nullable=True)
    line = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

# Асинхронный движок базы данных
async_engine = None
async_session = None

async def setup_database(config):
    global async_engine, async_session

    # Создание директории для базы данных
    config.data_dir.mkdir(parents=True, exist_ok=True)

    # Создание асинхронного движка
    async_engine = create_async_engine(config.db_url, echo=False)

    # Создание асинхронной сессии
    async_session = sessionmaker(
        async_engine, expire_on_commit=False, class_=AsyncSession
    )

    # Создание таблиц
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print(f"setup_database: async_session установлен как {async_session}")
    logger.info(f"База данных инициализирована: {config.db_path}")

# Функция для получения сессии БД
async def get_session():
    async with async_session() as session:
        yield session
