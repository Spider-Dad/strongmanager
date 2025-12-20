-- ============================================
-- PostgreSQL Schema for GetCourse Bot
-- ============================================
-- Версия: 1.0.0
-- Дата создания: 2025-12-20
-- Описание: Полная схема базы данных для бота управления GetCourse
--
-- ВАЖНО:
-- - Все справочные таблицы заполняются вручную через DBeaver
-- - Таблица webhook_events автоматически заполняется через n8n
-- - Таблица notifications автоматически заполняется ботом
-- ============================================

-- Установка схемы по умолчанию
SET search_path TO public;

-- ============================================
-- СПРАВОЧНЫЕ ТАБЛИЦЫ (РУЧНОЕ ЗАПОЛНЕНИЕ)
-- ============================================

-- Таблица наставников
CREATE TABLE IF NOT EXISTS mentors (
    id BIGSERIAL PRIMARY KEY,
    mentor_id INTEGER UNIQUE NOT NULL,            -- ID наставника в GetCourse
    telegram_id BIGINT UNIQUE,                    -- Telegram ID наставника
    email VARCHAR(255) UNIQUE NOT NULL,           -- Email наставника
    first_name VARCHAR(255),                      -- Имя
    last_name VARCHAR(255),                       -- Фамилия
    username VARCHAR(255),                        -- Telegram username

    -- Поля актуальности записи
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- Начало периода актуальности
    valid_to TIMESTAMPTZ DEFAULT '9999-12-31'::TIMESTAMPTZ,  -- Конец периода актуальности

    -- Аудит полей
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- Дата создания записи
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- Дата последнего обновления

    CONSTRAINT mentors_valid_period_check CHECK (valid_from <= valid_to)
);

-- Индексы для таблицы mentors
CREATE INDEX idx_mentors_telegram_id ON mentors(telegram_id) WHERE telegram_id IS NOT NULL;
CREATE INDEX idx_mentors_email ON mentors(email);
CREATE INDEX idx_mentors_valid_period ON mentors(valid_from, valid_to);
CREATE INDEX idx_mentors_active ON mentors(valid_from, valid_to) WHERE valid_to = '9999-12-31'::TIMESTAMPTZ;

COMMENT ON TABLE mentors IS 'Справочник наставников (заполняется вручную через DBeaver)';
COMMENT ON COLUMN mentors.valid_from IS 'Начало периода актуальности записи';
COMMENT ON COLUMN mentors.valid_to IS 'Конец периода актуальности (9999-12-31 = бессрочно)';


-- Таблица студентов
CREATE TABLE IF NOT EXISTS students (
    id BIGSERIAL PRIMARY KEY,
    student_id INTEGER UNIQUE NOT NULL,           -- ID студента в GetCourse
    user_email VARCHAR(255) NOT NULL,             -- Email студента
    first_name VARCHAR(255),                      -- Имя
    last_name VARCHAR(255),                       -- Фамилия

    -- Поля актуальности записи
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ DEFAULT '9999-12-31'::TIMESTAMPTZ,

    -- Аудит полей
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT students_valid_period_check CHECK (valid_from <= valid_to)
);

-- Индексы для таблицы students
CREATE INDEX idx_students_email ON students(user_email);
CREATE INDEX idx_students_valid_period ON students(valid_from, valid_to);
CREATE INDEX idx_students_active ON students(valid_from, valid_to) WHERE valid_to = '9999-12-31'::TIMESTAMPTZ;

COMMENT ON TABLE students IS 'Справочник студентов (заполняется вручную через DBeaver)';


-- Таблица тренингов
CREATE TABLE IF NOT EXISTS trainings (
    id BIGSERIAL PRIMARY KEY,
    training_id VARCHAR(50) UNIQUE NOT NULL,      -- ID тренинга в GetCourse
    title VARCHAR(255) NOT NULL,                  -- Название тренинга
    start_date TIMESTAMPTZ,                       -- Дата начала тренинга
    end_date TIMESTAMPTZ,                         -- Дата окончания тренинга

    -- Поля актуальности записи
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ DEFAULT '9999-12-31'::TIMESTAMPTZ,

    -- Аудит полей
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT trainings_valid_period_check CHECK (valid_from <= valid_to),
    CONSTRAINT trainings_dates_check CHECK (start_date IS NULL OR end_date IS NULL OR start_date <= end_date)
);

-- Индексы для таблицы trainings
CREATE INDEX idx_trainings_training_id ON trainings(training_id);
CREATE INDEX idx_trainings_dates ON trainings(start_date, end_date);
CREATE INDEX idx_trainings_valid_period ON trainings(valid_from, valid_to);
CREATE INDEX idx_trainings_active ON trainings(valid_from, valid_to) WHERE valid_to = '9999-12-31'::TIMESTAMPTZ;

COMMENT ON TABLE trainings IS 'Справочник тренингов (заполняется вручную через DBeaver)';


-- Таблица уроков
CREATE TABLE IF NOT EXISTS lessons (
    id BIGSERIAL PRIMARY KEY,
    lesson_id VARCHAR(50) UNIQUE NOT NULL,        -- ID урока в GetCourse
    training_id VARCHAR(50) NOT NULL,             -- ID тренинга
    module_number INTEGER,                        -- Номер модуля
    module_title VARCHAR(255),                    -- Название модуля
    lesson_number INTEGER,                        -- Номер урока
    lesson_title VARCHAR(255),                    -- Название урока
    opening_date TIMESTAMPTZ,                     -- Дата открытия урока
    deadline_date TIMESTAMPTZ,                    -- Дедлайн сдачи урока

    -- Поля актуальности записи
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ DEFAULT '9999-12-31'::TIMESTAMPTZ,

    -- Аудит полей
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT lessons_valid_period_check CHECK (valid_from <= valid_to),
    CONSTRAINT lessons_dates_check CHECK (opening_date IS NULL OR deadline_date IS NULL OR opening_date <= deadline_date)
);

-- Индексы для таблицы lessons
CREATE INDEX idx_lessons_lesson_id ON lessons(lesson_id);
CREATE INDEX idx_lessons_training_id ON lessons(training_id);
CREATE INDEX idx_lessons_deadline ON lessons(deadline_date) WHERE deadline_date IS NOT NULL;
CREATE INDEX idx_lessons_valid_period ON lessons(valid_from, valid_to);
CREATE INDEX idx_lessons_active ON lessons(valid_from, valid_to) WHERE valid_to = '9999-12-31'::TIMESTAMPTZ;

COMMENT ON TABLE lessons IS 'Справочник уроков (заполняется вручную через DBeaver)';
COMMENT ON COLUMN lessons.deadline_date IS 'Дедлайн для проверки приближающихся сроков';


-- Таблица сопоставления студентов и наставников
CREATE TABLE IF NOT EXISTS mapping (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL,                   -- ID студента (ссылка на students.id)
    mentor_id BIGINT NOT NULL,                    -- ID наставника (ссылка на mentors.id)
    training_id BIGINT NOT NULL,                  -- ID тренинга (ссылка на trainings.id)

    -- Поля актуальности записи
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ DEFAULT '9999-12-31'::TIMESTAMPTZ,

    -- Аудит полей
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT mapping_valid_period_check CHECK (valid_from <= valid_to),
    -- Уникальность: один студент может быть закреплен за одним ментором в рамках одного тренинга в один период времени
    CONSTRAINT mapping_unique_student_mentor_training UNIQUE (student_id, training_id, valid_from, valid_to)
);

-- Индексы для таблицы mapping
CREATE INDEX idx_mapping_student_id ON mapping(student_id);
CREATE INDEX idx_mapping_mentor_id ON mapping(mentor_id);
CREATE INDEX idx_mapping_training_id ON mapping(training_id);
CREATE INDEX idx_mapping_valid_period ON mapping(valid_from, valid_to);
CREATE INDEX idx_mapping_active ON mapping(valid_from, valid_to) WHERE valid_to = '9999-12-31'::TIMESTAMPTZ;

COMMENT ON TABLE mapping IS 'Сопоставление студентов и наставников (заполняется вручную через DBeaver)';


-- ============================================
-- ТАБЛИЦЫ ДАННЫХ (АВТОМАТИЧЕСКОЕ ЗАПОЛНЕНИЕ)
-- ============================================

-- Таблица вебхуков от GetCourse (заполняется через n8n)
CREATE TABLE IF NOT EXISTS webhook_events (
    id BIGSERIAL PRIMARY KEY,

    -- Поля из вебхука GetCourse
    event_date TIMESTAMPTZ NOT NULL,              -- Дата события
    user_id INTEGER NOT NULL,                     -- ID пользователя (студента)
    user_email VARCHAR(255) NOT NULL,             -- Email пользователя
    user_first_name VARCHAR(255),                 -- Имя пользователя
    user_last_name VARCHAR(255),                  -- Фамилия пользователя
    answer_id INTEGER NOT NULL,                   -- ID ответа
    answer_training_id INTEGER,                   -- ID тренинга
    answer_lesson_id INTEGER,                     -- ID урока
    answer_status VARCHAR(50),                    -- Статус ответа (completed, etc.)
    answer_text TEXT,                             -- Текст ответа
    answer_type VARCHAR(50),                      -- Тип ответа (new, etc.)
    answer_teacher_id INTEGER,                    -- ID проверяющего

    -- Служебные поля
    raw_payload JSONB,                            -- Полный JSON вебхука для отладки
    processed BOOLEAN DEFAULT FALSE,              -- Обработан ли вебхук ботом
    processed_at TIMESTAMPTZ,                     -- Когда обработан
    error_message TEXT,                           -- Ошибка при обработке (если была)

    -- Аудит
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW() -- Время получения вебхука
);

-- Индексы для таблицы webhook_events
CREATE INDEX idx_webhook_events_answer_id ON webhook_events(answer_id);
CREATE INDEX idx_webhook_events_user_id ON webhook_events(user_id);
CREATE INDEX idx_webhook_events_user_email ON webhook_events(user_email);
CREATE INDEX idx_webhook_events_training_lesson ON webhook_events(answer_training_id, answer_lesson_id);
CREATE INDEX idx_webhook_events_processed ON webhook_events(processed, created_at) WHERE processed = FALSE;
CREATE INDEX idx_webhook_events_event_date ON webhook_events(event_date DESC);
CREATE INDEX idx_webhook_events_created_at ON webhook_events(created_at DESC);

-- GIN индекс для поиска по JSONB
CREATE INDEX idx_webhook_events_raw_payload ON webhook_events USING GIN (raw_payload);

COMMENT ON TABLE webhook_events IS 'Вебхуки от GetCourse (автоматически заполняется через n8n)';
COMMENT ON COLUMN webhook_events.processed IS 'FALSE = требует обработки ботом';
COMMENT ON COLUMN webhook_events.raw_payload IS 'Полный JSON вебхука для отладки и восстановления';


-- Таблица уведомлений (заполняется ботом)
CREATE TABLE IF NOT EXISTS notifications (
    id BIGSERIAL PRIMARY KEY,
    mentor_id BIGINT NOT NULL,                    -- ID наставника из таблицы mentors
    type VARCHAR(50) NOT NULL,                    -- Тип: answerToLesson, deadlineApproaching, etc.
    message TEXT NOT NULL,                        -- Текст уведомления для отправки
    status VARCHAR(20) DEFAULT 'pending',         -- pending, sent, failed

    -- Связь с вебхуком-источником (если применимо)
    webhook_event_id BIGINT,                      -- Ссылка на webhook_events.id

    -- Метаданные для дедупликации
    message_hash VARCHAR(64),                     -- SHA256 хеш для предотвращения дубликатов

    -- Даты
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ,                          -- Время отправки

    -- Telegram метаданные
    telegram_message_id VARCHAR(50),              -- ID сообщения в Telegram

    CONSTRAINT notifications_status_check CHECK (status IN ('pending', 'sent', 'failed'))
);

-- Индексы для таблицы notifications
CREATE INDEX idx_notifications_mentor_id ON notifications(mentor_id);
CREATE INDEX idx_notifications_status ON notifications(status, created_at) WHERE status = 'pending';
CREATE INDEX idx_notifications_type ON notifications(type);
CREATE INDEX idx_notifications_created_at ON notifications(created_at DESC);
CREATE INDEX idx_notifications_message_hash ON notifications(message_hash) WHERE message_hash IS NOT NULL;
CREATE INDEX idx_notifications_webhook_event_id ON notifications(webhook_event_id) WHERE webhook_event_id IS NOT NULL;

COMMENT ON TABLE notifications IS 'Уведомления для наставников (автоматически создаются ботом)';
COMMENT ON COLUMN notifications.message_hash IS 'SHA256 хеш для предотвращения дубликатов уведомлений';


-- ============================================
-- СЛУЖЕБНЫЕ ТАБЛИЦЫ
-- ============================================

-- Таблица логов приложения
CREATE TABLE IF NOT EXISTS application_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    level VARCHAR(20) NOT NULL,                   -- DEBUG, INFO, WARNING, ERROR, CRITICAL
    logger_name VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    module VARCHAR(255),
    function VARCHAR(255),
    line INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Индексы для таблицы application_logs
CREATE INDEX idx_application_logs_timestamp ON application_logs(timestamp DESC);
CREATE INDEX idx_application_logs_level ON application_logs(level, timestamp DESC);
CREATE INDEX idx_application_logs_logger_name ON application_logs(logger_name);

COMMENT ON TABLE application_logs IS 'Логи приложения для отладки';


-- Таблица логов ошибок (для быстрого доступа)
CREATE TABLE IF NOT EXISTS error_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    level VARCHAR(20) NOT NULL,                   -- WARNING, ERROR, CRITICAL
    logger_name VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    traceback TEXT,
    module VARCHAR(255),
    function VARCHAR(255),
    line INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Индексы для таблицы error_logs
CREATE INDEX idx_error_logs_timestamp ON error_logs(timestamp DESC);
CREATE INDEX idx_error_logs_level ON error_logs(level);

COMMENT ON TABLE error_logs IS 'Только ошибки и предупреждения для быстрого анализа';


-- ============================================
-- ТРИГГЕРЫ ДЛЯ АВТОМАТИЧЕСКОГО ОБНОВЛЕНИЯ updated_at
-- ============================================

-- Функция для обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггеры для справочных таблиц
DROP TRIGGER IF EXISTS update_mentors_updated_at ON mentors;
CREATE TRIGGER update_mentors_updated_at BEFORE UPDATE ON mentors
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_students_updated_at ON students;
CREATE TRIGGER update_students_updated_at BEFORE UPDATE ON students
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_trainings_updated_at ON trainings;
CREATE TRIGGER update_trainings_updated_at BEFORE UPDATE ON trainings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_lessons_updated_at ON lessons;
CREATE TRIGGER update_lessons_updated_at BEFORE UPDATE ON lessons
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_mapping_updated_at ON mapping;
CREATE TRIGGER update_mapping_updated_at BEFORE UPDATE ON mapping
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================
-- ФУНКЦИИ ДЛЯ РАБОТЫ С АКТУАЛЬНЫМИ ЗАПИСЯМИ
-- ============================================

-- Функция для получения актуальных записей на текущую дату
COMMENT ON FUNCTION update_updated_at_column() IS 'Автоматически обновляет поле updated_at при изменении записи';

-- Пример использования актуальности:
-- SELECT * FROM mentors WHERE CURRENT_TIMESTAMP BETWEEN valid_from AND valid_to;
-- SELECT * FROM students WHERE valid_to = '9999-12-31'::TIMESTAMPTZ;  -- только активные


-- ============================================
-- ПРЕДСТАВЛЕНИЯ (VIEWS) ДЛЯ УДОБСТВА
-- ============================================

-- Представление для активных наставников
CREATE OR REPLACE VIEW v_active_mentors AS
SELECT *
FROM mentors
WHERE CURRENT_TIMESTAMP BETWEEN valid_from AND valid_to;

COMMENT ON VIEW v_active_mentors IS 'Только актуальные на текущий момент наставники';


-- Представление для активных студентов
CREATE OR REPLACE VIEW v_active_students AS
SELECT *
FROM students
WHERE CURRENT_TIMESTAMP BETWEEN valid_from AND valid_to;

COMMENT ON VIEW v_active_students IS 'Только актуальные на текущий момент студенты';


-- Представление для активных маппингов
CREATE OR REPLACE VIEW v_active_mappings AS
SELECT
    m.*,
    s.user_email as student_email,
    s.first_name as student_first_name,
    s.last_name as student_last_name,
    mentor.email as mentor_email,
    mentor.first_name as mentor_first_name,
    mentor.last_name as mentor_last_name,
    mentor.telegram_id as mentor_telegram_id
FROM mapping m
JOIN students s ON m.student_id = s.id
JOIN mentors mentor ON m.mentor_id = mentor.id
WHERE CURRENT_TIMESTAMP BETWEEN m.valid_from AND m.valid_to
  AND CURRENT_TIMESTAMP BETWEEN s.valid_from AND s.valid_to
  AND CURRENT_TIMESTAMP BETWEEN mentor.valid_from AND mentor.valid_to;

COMMENT ON VIEW v_active_mappings IS 'Активные связи студент-ментор с полной информацией';


-- Представление для необработанных вебхуков
CREATE OR REPLACE VIEW v_pending_webhooks AS
SELECT *
FROM webhook_events
WHERE processed = FALSE
ORDER BY created_at ASC;

COMMENT ON VIEW v_pending_webhooks IS 'Вебхуки, ожидающие обработки ботом';


-- Представление для неотправленных уведомлений
CREATE OR REPLACE VIEW v_pending_notifications AS
SELECT
    n.*,
    m.telegram_id,
    m.email as mentor_email,
    m.first_name as mentor_first_name,
    m.last_name as mentor_last_name
FROM notifications n
JOIN mentors m ON n.mentor_id = m.id
WHERE n.status = 'pending'
  AND m.telegram_id IS NOT NULL
  AND CURRENT_TIMESTAMP BETWEEN m.valid_from AND m.valid_to
ORDER BY n.created_at ASC;

COMMENT ON VIEW v_pending_notifications IS 'Уведомления, готовые к отправке';


-- ============================================
-- НАЧАЛЬНЫЕ ДАННЫЕ (опционально)
-- ============================================

-- Вставка тестовых данных отключена
-- Все справочники заполняются вручную через DBeaver


-- ============================================
-- ИНФОРМАЦИЯ О СХЕМЕ
-- ============================================

COMMENT ON SCHEMA public IS 'Схема базы данных GetCourse Bot - v1.0.0';

-- Конец schema.sql
