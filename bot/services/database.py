"""
SQLAlchemy модели и конфигурация базы данных для GetCourse Bot

Использует PostgreSQL (asyncpg) для всех окружений (dev/prod)

Версия: 2.0.0 (PostgreSQL only)
"""

import logging

from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)

# Базовый класс для моделей SQLAlchemy
Base = declarative_base()


# ============================================
# СПРАВОЧНЫЕ МОДЕЛИ (РУЧНОЕ ЗАПОЛНЕНИЕ ЧЕРЕЗ DBeaver)
# ============================================

class Mentor(Base):
    """
    Модель наставника
    Заполняется вручную через DBeaver
    """
    __tablename__ = "mentors"

    id = Column(BigInteger, primary_key=True)
    mentor_id = Column(Integer, unique=True, nullable=False)
    telegram_id = Column(BigInteger, unique=True, nullable=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    username = Column(String(255), nullable=True)

    # Поля актуальности записи
    valid_from = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    valid_to = Column(TIMESTAMP(timezone=True), nullable=False,
                     server_default="'9999-12-31'::timestamptz")

    # Аудит
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False,
                       server_default=func.now(), onupdate=func.now())


class Student(Base):
    """
    Модель студента
    Заполняется вручную через DBeaver
    """
    __tablename__ = "students"

    id = Column(BigInteger, primary_key=True)
    student_id = Column(Integer, unique=True, nullable=False)
    user_email = Column(String(255), nullable=False, index=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)

    # Поля актуальности записи
    valid_from = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    valid_to = Column(TIMESTAMP(timezone=True), nullable=False,
                     server_default="'9999-12-31'::timestamptz")

    # Аудит
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False,
                       server_default=func.now(), onupdate=func.now())


class Training(Base):
    """
    Модель тренинга
    Заполняется вручную через DBeaver
    """
    __tablename__ = "trainings"

    id = Column(BigInteger, primary_key=True)
    training_id = Column(String(50), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    start_date = Column(TIMESTAMP(timezone=True), nullable=True)
    end_date = Column(TIMESTAMP(timezone=True), nullable=True)

    # Поля актуальности записи
    valid_from = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    valid_to = Column(TIMESTAMP(timezone=True), nullable=False,
                     server_default="'9999-12-31'::timestamptz")

    # Аудит
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False,
                       server_default=func.now(), onupdate=func.now())


class Lesson(Base):
    """
    Модель урока
    Заполняется вручную через DBeaver
    """
    __tablename__ = "lessons"

    id = Column(BigInteger, primary_key=True)
    lesson_id = Column(String(50), unique=True, nullable=False, index=True)
    training_id = Column(String(50), nullable=False, index=True)
    module_number = Column(Integer, nullable=True)
    module_title = Column(String(255), nullable=True)
    lesson_number = Column(Integer, nullable=True)
    lesson_title = Column(String(255), nullable=True)
    opening_date = Column(TIMESTAMP(timezone=True), nullable=True)
    deadline_date = Column(TIMESTAMP(timezone=True), nullable=True, index=True)

    # Поля актуальности записи
    valid_from = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    valid_to = Column(TIMESTAMP(timezone=True), nullable=False,
                     server_default="'9999-12-31'::timestamptz")

    # Аудит
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False,
                       server_default=func.now(), onupdate=func.now())


class Mapping(Base):
    """
    Модель сопоставления студент-ментор-тренинг
    Заполняется вручную через DBeaver
    """
    __tablename__ = "mapping"

    id = Column(BigInteger, primary_key=True)
    student_id = Column(BigInteger, nullable=False, index=True)
    mentor_id = Column(BigInteger, nullable=False, index=True)
    training_id = Column(BigInteger, nullable=False, index=True)

    # Поля актуальности записи
    valid_from = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    valid_to = Column(TIMESTAMP(timezone=True), nullable=False,
                     server_default="'9999-12-31'::timestamptz")

    # Аудит
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False,
                       server_default=func.now(), onupdate=func.now())


# ============================================
# МОДЕЛИ ДАННЫХ (АВТОМАТИЧЕСКОЕ ЗАПОЛНЕНИЕ)
# ============================================

class WebhookEvent(Base):
    """
    Модель вебхука от GetCourse
    Автоматически заполняется через n8n workflow
    Обрабатывается ботом через WebhookProcessingService
    """
    __tablename__ = "webhook_events"

    id = Column(BigInteger, primary_key=True)

    # Поля из вебхука GetCourse
    event_date = Column(TIMESTAMP(timezone=True), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    user_email = Column(String(255), nullable=False, index=True)
    user_first_name = Column(String(255), nullable=True)
    user_last_name = Column(String(255), nullable=True)
    answer_id = Column(Integer, nullable=False, index=True)
    answer_training_id = Column(Integer, nullable=True, index=True)
    answer_lesson_id = Column(Integer, nullable=True, index=True)
    answer_status = Column(String(50), nullable=True)
    answer_text = Column(Text, nullable=True)
    answer_type = Column(String(50), nullable=True)
    answer_teacher_id = Column(Integer, nullable=True)

    # Служебные поля
    raw_payload = Column(JSONB, nullable=True)  # Полный JSON для отладки
    processed = Column(Boolean, default=False, nullable=False, index=True)
    processed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    # Аудит
    created_at = Column(TIMESTAMP(timezone=True), nullable=False,
                       server_default=func.now(), index=True)


class Notification(Base):
    """
    Модель уведомления для ментора
    Автоматически создается ботом на основе webhook_events
    Отправляется через NotificationSenderService
    """
    __tablename__ = "notifications"

    id = Column(BigInteger, primary_key=True)
    mentor_id = Column(BigInteger, nullable=False, index=True)
    type = Column(String(50), nullable=False, index=True)
    message = Column(Text, nullable=False)
    status = Column(String(20), default="pending", nullable=False, index=True)

    # Связь с вебхуком-источником
    webhook_event_id = Column(BigInteger, nullable=True, index=True)

    # Метаданные для дедупликации
    message_hash = Column(String(64), nullable=True, index=True)

    # Даты
    created_at = Column(TIMESTAMP(timezone=True), nullable=False,
                       server_default=func.now(), index=True)
    sent_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Telegram метаданные
    telegram_message_id = Column(String(50), nullable=True)


# ============================================
# СЛУЖЕБНЫЕ МОДЕЛИ
# ============================================

class Log(Base):
    """
    DEPRECATED: Используется только для обратной совместимости
    Новые логи пишутся в application_logs
    """
    __tablename__ = "logs"

    id = Column(BigInteger, primary_key=True)
    date = Column(TIMESTAMP(timezone=True), nullable=True)
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
    webhook_date = Column(TIMESTAMP(timezone=True), nullable=True)


class WebhookRawLog(Base):
    """
    DEPRECATED: Используется только для обратной совместимости
    Вебхуки теперь хранятся в webhook_events.raw_payload (JSONB)
    """
    __tablename__ = "webhook_raw_log"

    id = Column(BigInteger, primary_key=True)
    date = Column(TIMESTAMP(timezone=True), nullable=True)
    raw_data = Column(Text, nullable=True)


class DebugLog(Base):
    """
    DEPRECATED: Используется только для обратной совместимости
    Отладочные логи теперь пишутся в application_logs
    """
    __tablename__ = "debug_log"

    id = Column(BigInteger, primary_key=True)
    date = Column(TIMESTAMP(timezone=True), nullable=True)
    event = Column(String(255), nullable=True)
    data = Column(Text, nullable=True)


class ApplicationLog(Base):
    """
    Модель для хранения логов приложения
    """
    __tablename__ = "application_logs"

    id = Column(BigInteger, primary_key=True)
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False,
                      server_default=func.now(), index=True)
    level = Column(String(20), nullable=False, index=True)
    logger_name = Column(String(255), nullable=False, index=True)
    message = Column(Text, nullable=False)
    module = Column(String(255), nullable=True)
    function = Column(String(255), nullable=True)
    line = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class ErrorLog(Base):
    """
    Модель для хранения ошибок приложения (для быстрого доступа)
    """
    __tablename__ = "error_logs"

    id = Column(BigInteger, primary_key=True)
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False,
                      server_default=func.now(), index=True)
    level = Column(String(20), nullable=False, index=True)
    logger_name = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    traceback = Column(Text, nullable=True)
    module = Column(String(255), nullable=True)
    function = Column(String(255), nullable=True)
    line = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


# ============================================
# АСИНХРОННЫЙ ДВИЖОК И СЕССИЯ
# ============================================

async_engine = None
async_session = None


async def setup_database(config):
    """
    Инициализация базы данных PostgreSQL

    Args:
        config: Объект конфигурации бота
    """
    global async_engine, async_session

    logger.info(f"Инициализация PostgreSQL БД: {config.db_url}")

    # PostgreSQL конфигурация
    async_engine = create_async_engine(
        config.db_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,  # Размер пула соединений
        max_overflow=20,  # Максимум дополнительных соединений
        pool_recycle=3600,  # Пересоздание соединений каждый час
        connect_args=config.db_connect_args
    )

    logger.info(f"PostgreSQL: подключение к {config.postgres_host}:{config.postgres_port}/{config.postgres_db}")

    # Создание асинхронной сессии
    async_session = sessionmaker(
        async_engine,
        expire_on_commit=False,
        class_=AsyncSession
    )

    # Таблицы создаются через schema.sql (не автоматически)
    logger.info("PostgreSQL: таблицы должны быть созданы через db/schema.sql или db/init_database.py")

    logger.info(f"База данных инициализирована: {config.db_url}")

    # Проверяем доступность базы данных
    try:
        async with async_session() as session:
            # Пробуем выполнить простой запрос
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
            logger.info("✓ Проверка подключения к БД успешна")
    except Exception as e:
        logger.error(f"✗ Ошибка при проверке подключения к БД: {e}")
        raise


async def get_session():
    """
    Генератор для получения асинхронной сессии БД

    Использование:
        async for session in get_session():
            # работа с сессией
            pass
    """
    async with async_session() as session:
        yield session
