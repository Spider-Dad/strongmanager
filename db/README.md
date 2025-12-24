# База данных GetCourse Bot - PostgreSQL

Версия: 2.0.0
Дата: 2025-12-20
Статус: Phase 1 - PostgreSQL Schema & Models

## Обзор

База данных GetCourse Bot мигрирована с SQLite на PostgreSQL для поддержки:
- Высокой нагрузки (конкурентные запросы от n8n и бота)
- JSONB для хранения raw webhook данных
- Расширенных индексов и представлений
- Временной актуальности записей (valid_from, valid_to)

## Архитектура базы данных

### Типы таблиц

1. **Справочные таблицы** (заполняются вручную через DBeaver):
   - `mentors` - наставники
   - `students` - студенты
   - `trainings` - тренинги
   - `lessons` - уроки
   - `mapping` - связи студент-ментор-тренинг

2. **Таблицы данных** (автоматическое заполнение):
   - `webhook_events` - вебхуки от GetCourse (через n8n)
   - `notifications` - уведомления для отправки (через бота)

3. **Служебные таблицы**:
   - `application_logs` - логи приложения
   - `error_logs` - логи ошибок
   - Устаревшие таблицы для обратной совместимости

## Поля актуальности записей

Все справочные таблицы имеют поля временной актуальности:

- `valid_from` - начало периода актуальности (по умолчанию NOW())
- `valid_to` - конец периода актуальности (по умолчанию '9999-12-31')
- `created_at` - дата создания записи
- `updated_at` - дата последнего обновления (автоматически)

### Работа с актуальностью

**Получение актуальных записей на текущий момент:**
```sql
SELECT * FROM mentors
WHERE CURRENT_TIMESTAMP BETWEEN valid_from AND valid_to;
```

**Получение только активных (бессрочных) записей:**
```sql
SELECT * FROM students
WHERE valid_to = '9999-12-31'::TIMESTAMPTZ;
```

**Использование представлений:**
```sql
-- Готовые представления для актуальных данных
SELECT * FROM v_active_mentors;
SELECT * FROM v_active_students;
SELECT * FROM v_active_mappings;
```

**Закрытие актуальности записи (например, при увольнении ментора):**
```sql
UPDATE mentors
SET valid_to = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
WHERE id = 123;
```

**Создание новой версии записи:**
```sql
-- 1. Закрываем старую запись
UPDATE mentors
SET valid_to = CURRENT_TIMESTAMP
WHERE id = 123;

-- 2. Создаем новую с обновленными данными
INSERT INTO mentors (email, first_name, last_name, telegram_id, valid_from, valid_to)
VALUES ('mentor@example.com', 'Новое', 'Имя', 123456789, CURRENT_TIMESTAMP, '9999-12-31'::TIMESTAMPTZ);
```

## Настройка подключения

### Переменные окружения (.env)

```bash
# Тип БД
DB_TYPE=postgresql

# PostgreSQL настройки
POSTGRES_HOST_EXTERNAL=getcoursebd-spiderdad.db-msk0.amvera.tech  # Для dev
POSTGRES_HOST_INTERNAL=amvera-spiderdad-cnpg-getcoursebd-rw       # Для prod
POSTGRES_PORT=5432
POSTGRES_USER=postgresql
POSTGRES_PASSWORD=your_password_here
POSTGRES_DB=GetCourseBD
POSTGRES_SCHEMA=public

# Окружение
SERVER_ENV=dev  # или prod
```

### Автоматический выбор хоста

Конфигурация автоматически выбирает хост в зависимости от окружения:
- **Dev**: использует `POSTGRES_HOST_EXTERNAL` (доступ из интернета)
- **Prod**: использует `POSTGRES_HOST_INTERNAL` (внутреннее доменное имя Amvera)

## Инициализация базы данных

### Шаг 1: Установка зависимостей

```bash
cd getcourse_bot
pip install -r requirements.txt
```

Будут установлены:
- `asyncpg>=0.29.0` - асинхронный драйвер PostgreSQL
- `psycopg2-binary>=2.9.9` - синхронный драйвер (для совместимости)
- `SQLAlchemy==2.0.25` - ORM

### Шаг 2: Настройка .env

Скопируйте `env.example` в `.env` и заполните параметры PostgreSQL:

```bash
cp env.example .env
# Отредактируйте .env, установите POSTGRES_PASSWORD
```

### Шаг 3: Запуск скрипта инициализации

```bash
python db/init_database.py
```

Скрипт выполнит:
1. Проверку подключения к PostgreSQL
2. Создание всех таблиц из `schema.sql`
3. Создание индексов и представлений
4. Вывод статистики созданных объектов

### Шаг 4: Заполнение справочных данных

**Через DBeaver:**
1. Подключитесь к PostgreSQL
2. Откройте таблицы: `mentors`, `students`, `trainings`, `lessons`, `mapping`
3. Заполните данные вручную

**Важно:** Используйте правильные значения для `valid_from` и `valid_to`:
- `valid_from` = дата начала актуальности (обычно NOW())
- `valid_to` = '9999-12-31' для бессрочных записей

## Структура схемы

### Таблица webhook_events

Вебхуки от GetCourse (автозаполнение через n8n):

```sql
CREATE TABLE webhook_events (
    id BIGSERIAL PRIMARY KEY,
    event_date TIMESTAMPTZ NOT NULL,
    user_id VARCHAR(50) NOT NULL,
    user_email VARCHAR(255) NOT NULL,
    answer_id VARCHAR(50) NOT NULL,
    answer_training_id VARCHAR(50),
    answer_lesson_id VARCHAR(50),
    answer_status VARCHAR(50),
    answer_text TEXT,
    raw_payload JSONB,              -- Полный JSON вебхука
    processed BOOLEAN DEFAULT FALSE, -- Обработан ботом?
    processed_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Таблица notifications

Уведомления для менторов (автозаполнение ботом):

```sql
CREATE TABLE notifications (
    id BIGSERIAL PRIMARY KEY,
    mentor_id BIGINT NOT NULL,
    type VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    webhook_event_id BIGINT,
    message_hash VARCHAR(64),        -- Для дедупликации
    created_at TIMESTAMPTZ DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    telegram_message_id VARCHAR(50)
);
```

## Представления (Views)

Готовые представления для работы с актуальными данными:

### v_active_mentors
Только актуальные наставники на текущий момент:
```sql
SELECT * FROM v_active_mentors;
```

### v_active_mappings
Активные связи студент-ментор с полной информацией:
```sql
SELECT * FROM v_active_mappings
WHERE training_id = 'training-001';
```

### v_pending_webhooks
Вебхуки, ожидающие обработки:
```sql
SELECT * FROM v_pending_webhooks
LIMIT 10;
```

### v_pending_notifications
Уведомления, готовые к отправке:
```sql
SELECT * FROM v_pending_notifications;
```

## Индексы

Все таблицы имеют оптимизированные индексы:

### Основные индексы
- **Primary Key** на всех таблицах (BIGSERIAL id)
- **Email индексы** для быстрого поиска пользователей
- **Composite индексы** для частых JOIN операций
- **Partial индексы** для актуальных записей

### Специальные индексы
- **GIN индекс** на `webhook_events.raw_payload` для поиска по JSONB
- **B-tree индексы** на `valid_from` и `valid_to` для временных запросов
- **Partial индексы** на `processed=FALSE` для необработанных вебхуков

## Триггеры

### Автоматическое обновление updated_at

Для всех справочных таблиц создан триггер автоматического обновления `updated_at`:

```sql
CREATE TRIGGER update_mentors_updated_at
BEFORE UPDATE ON mentors
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

При любом UPDATE запросе поле `updated_at` автоматически обновляется на `NOW()`.

## Миграция с SQLite

Если у вас была SQLite база данных, **НЕ** мигрируйте данные автоматически.

**Процесс:**
1. Старые данные из SQLite остаются как архив
2. Справочные таблицы PostgreSQL заполняются вручную через DBeaver
3. Вебхуки начнут поступать в PostgreSQL через n8n
4. Бот переключается на PostgreSQL через переменную `DB_TYPE=postgresql`

## Мониторинг и обслуживание

### Проверка необработанных вебхуков

```sql
SELECT COUNT(*) as pending_count
FROM webhook_events
WHERE processed = FALSE;
```

### Проверка неотправленных уведомлений

```sql
SELECT COUNT(*) as pending_notifications
FROM notifications
WHERE status = 'pending';
```

### Очистка старых логов

```sql
-- Удаление логов старше 30 дней
DELETE FROM application_logs
WHERE created_at < NOW() - INTERVAL '30 days';

DELETE FROM error_logs
WHERE created_at < NOW() - INTERVAL '90 days';
```

### Анализ производительности

```sql
-- Самые медленные запросы
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;

-- Размер таблиц
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

## Backup и восстановление

### Создание резервной копии

```bash
# Полный дамп БД
pg_dump -h getcoursebd-spiderdad.db-msk0.amvera.tech \
        -p 5432 \
        -U postgresql \
        -d GetCourseBD \
        -F c \
        -f backup_$(date +%Y%m%d).dump

# Только схема (без данных)
pg_dump -h getcoursebd-spiderdad.db-msk0.amvera.tech \
        -p 5432 \
        -U postgresql \
        -d GetCourseBD \
        --schema-only \
        -f schema_backup.sql
```

### Восстановление из резервной копии

```bash
pg_restore -h getcoursebd-spiderdad.db-msk0.amvera.tech \
           -p 5432 \
           -U postgresql \
           -d GetCourseBD \
           -c \
           backup_20251220.dump
```

## Troubleshooting

### Проблема: TimeoutError или Connection refused

**Причина:** Неверный хост, порт или имя пользователя

**Решение:**
- Dev: используйте `POSTGRES_HOST_EXTERNAL`
- Prod: используйте `POSTGRES_HOST_INTERNAL`
- Проверьте порт (5432)
- **Важно**: Имя пользователя должно быть `postresql` (не `postgresql`)
- Увеличен таймаут подключения до 60 секунд

**Проверка доступности порта:**
```powershell
Test-NetConnection -ComputerName getcoursebd-spiderdad.db-msk0.amvera.tech -Port 5432
# Ожидаемый результат: TcpTestSucceeded : True
```

### Проблема: Invalid password

**Причина:** Неверный пароль в .env

**Решение:**
```bash
# Проверьте пароль
echo $POSTGRES_PASSWORD

# Обновите .env
POSTGRES_PASSWORD=correct_password
```

### Проблема: Таблицы не создаются

**Причина:** Скрипт инициализации не выполнен или выполнен с ошибками

**Решение:**
```bash
# Пересоздайте схему
python db/init_database.py

# Или вручную через psql
psql -h getcoursebd-spiderdad.db-msk0.amvera.tech \
     -p 5432 \
     -U postgresql \
     -d GetCourseBD \
     -f db/schema.sql
```

## Дальнейшие шаги

После успешной инициализации БД:

1. ✅ **Фаза 1 завершена** - PostgreSQL схема и модели готовы
2. ⏭️ **Фаза 2** - Обновление n8n workflow для записи в `webhook_events`
3. ⏭️ **Фаза 3** - Миграция бизнес-логики из GAS в Python сервисы
4. ⏭️ **Фаза 4** - Настройка APScheduler для обработки вебхуков
5. ⏭️ **Фаза 5** - Тестирование и переключение production

## Контакты и поддержка

При возникновении проблем:
- Проверьте логи бота: `data/logs/`
- Проверьте PostgreSQL логи на Amvera
- Используйте DBeaver для прямого доступа к БД

---

**Документация актуальна на: 2025-12-20**
**Версия схемы: 1.0.0**
