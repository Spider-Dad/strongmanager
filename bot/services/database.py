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
    telegram_id = Column(Integer, unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    username = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

# Модель для хранения истории уведомлений
class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    notification_id = Column(String(255), nullable=False)  # ID уведомления из Google Sheets
    mentor_id = Column(Integer, nullable=False)
    type = Column(String(50), nullable=False)  # Тип уведомления: answerToLesson, commentOnLesson, etc.
    message = Column(Text, nullable=False)  # Сообщение уведомления
    status = Column(String(20), default="pending")  # pending, sent, failed
    created_at = Column(DateTime, server_default=func.now())
    sent_at = Column(DateTime, nullable=True)

# Асинхронный движок базы данных
async_engine = None
async_session = None

async def setup_database(config):
    global async_engine, async_session

    # Создание директории для базы данных
    config.db_dir.mkdir(parents=True, exist_ok=True)

    # Создание асинхронного движка
    async_engine = create_async_engine(config.db_url, echo=False)

    # Создание асинхронной сессии
    async_session = sessionmaker(
        async_engine, expire_on_commit=False, class_=AsyncSession
    )

    # Создание таблиц
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info(f"База данных инициализирована: {config.db_path}")

# Функция для получения сессии БД
async def get_session():
    async with async_session() as session:
        yield session
