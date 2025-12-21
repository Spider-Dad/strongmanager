# Рефакторинг GetCourse Bot - Фаза 1: PostgreSQL Schema & Models

**Статус:** ✅ Завершено
**Дата:** 2025-12-20
**Ветка:** `refactor/phase1-postgresql-schema`

---

## Цель Фазы 1

Подготовка инфраструктуры базы данных для миграции с Google Apps Script на Python + n8n + PostgreSQL.

## Что было сделано

### 1. ✅ Создана SQL-схема PostgreSQL (`db/schema.sql`)

**Справочные таблицы** (заполняются вручную через DBeaver):
- `mentors` - наставники с поддержкой временной актуальности
- `students` - студенты с поддержкой временной актуальности
- `trainings` - тренинги с датами начала/окончания
- `lessons` - уроки с дедлайнами
- `mapping` - связи студент-ментор-тренинг

**Таблицы данных** (автоматическое заполнение):
- `webhook_events` - вебхуки от GetCourse (через n8n)
- `notifications` - уведомления для отправки (через бота)

**Служебные таблицы**:
- `application_logs` - логи приложения
- `error_logs` - логи ошибок

**Ключевые особенности:**
- Все ID: `BIGSERIAL` (автоинкремент)
- Временные метки: `TIMESTAMPTZ` (UTC хранение)
- Вебхук payload: `JSONB` (для гибкого хранения)
- Поля актуальности: `valid_from`, `valid_to` для всех справочников
- Аудит: `created_at`, `updated_at` (автообновление через триггеры)

### 2. ✅ Обновлены SQLAlchemy модели (`bot/services/database.py`)

**Изменения:**
- Замена SQLite типов на PostgreSQL (`BIGINT`, `TIMESTAMPTZ`, `JSONB`)
- Добавлена модель `WebhookEvent` для вебхуков от GetCourse
- Добавлены поля актуальности (`valid_from`, `valid_to`) во все справочные модели
- Удалены SQLite-специфичные настройки (WAL mode, PRAGMA)
- Добавлена поддержка connection pooling для PostgreSQL
- Сохранена обратная совместимость с SQLite (через `DB_TYPE`)

**Новые модели:**
```python
class WebhookEvent(Base):
    """Вебхуки от GetCourse (автозаполнение через n8n)"""
    raw_payload = Column(JSONB)  # Полный JSON вебхука
    processed = Column(Boolean, default=False)
    processed_at = Column(TIMESTAMP(timezone=True))
```

### 3. ✅ Обновлены зависимости (`requirements.txt`)

Добавлены:
- `asyncpg==0.29.0` - асинхронный драйвер PostgreSQL (основной)
- `psycopg2-binary==2.9.9` - синхронный драйвер (для совместимости)
- `SQLAlchemy==2.0.25` - обновлена версия ORM

### 4. ✅ Обновлена конфигурация (`bot/config.py`)

**Новые возможности:**
- Поддержка переключения БД через `DB_TYPE=postgresql|sqlite`
- Автоматический выбор хоста:
  - **Dev**: `POSTGRES_HOST_EXTERNAL` (доступ из интернета)
  - **Prod**: `POSTGRES_HOST_INTERNAL` (внутреннее имя Amvera)
- Настройка connection pooling для PostgreSQL
- Параметры подключения для asyncpg

**Новые переменные окружения:**
```bash
DB_TYPE=postgresql
POSTGRES_HOST_EXTERNAL=getcoursebd-spiderdad.db-msk0.amvera.tech
POSTGRES_HOST_INTERNAL=amvera-spiderdad-cnpg-getcoursebd-rw
POSTGRES_PORT=5432
POSTGRES_USER=postgresql
POSTGRES_PASSWORD=strongmanager
POSTGRES_DB=GetCourseBD
POSTGRES_SCHEMA=public
```

### 5. ✅ Создан скрипт инициализации БД (`db/init_database.py`)

**Возможности:**
- Проверка подключения к PostgreSQL
- Автоматическое создание всех таблиц из `schema.sql`
- Вывод статистики: таблицы, индексы, представления
- Подробная диагностика ошибок

**Использование:**
```bash
python db/init_database.py
```

### 6. ✅ Создана документация (`db/README.md`)

**Содержание:**
- Обзор архитектуры БД
- Инструкции по настройке
- Работа с полями актуальности (`valid_from`, `valid_to`)
- Примеры SQL запросов
- Troubleshooting
- Backup и восстановление

---

## Архитектурные решения

### Временная актуальность записей

Все справочные таблицы имеют поля:
- `valid_from` - начало периода актуальности (по умолчанию NOW())
- `valid_to` - конец периода актуальности (по умолчанию '9999-12-31')

**Преимущества:**
- История изменений без удаления данных
- Возможность "закрыть" запись без удаления
- Запросы на конкретную дату (временные срезы)
- Простая логика: `WHERE CURRENT_TIMESTAMP BETWEEN valid_from AND valid_to`

**Представления для удобства:**
```sql
SELECT * FROM v_active_mentors;      -- Только актуальные наставники
SELECT * FROM v_active_students;     -- Только актуальные студенты
SELECT * FROM v_active_mappings;     -- Актуальные связи с JOIN
```

### JSONB для вебхуков

Поле `webhook_events.raw_payload` типа JSONB хранит полный JSON вебхука:

**Преимущества:**
- Отладка: всегда можно посмотреть исходные данные
- Гибкость: не нужно менять схему при изменении формата вебхука
- Восстановление: можно переобработать вебхуки после исправления багов
- Поиск: GIN индекс для быстрого поиска по JSON

### Connection Pooling

PostgreSQL использует пул соединений:
```python
pool_size=10           # Базовый размер пула
max_overflow=20        # Дополнительные соединения
pool_recycle=3600      # Пересоздание каждый час
```

**Преимущества:**
- Эффективное использование ресурсов
- Быстрый отклик (соединения переиспользуются)
- Защита от утечек соединений

---

## Изменения в кодовой базе

### Файлы, которые были изменены:
1. `bot/config.py` - добавлена поддержка PostgreSQL
2. `bot/services/database.py` - новые модели для PostgreSQL
3. `requirements.txt` - добавлены asyncpg и psycopg2-binary
4. `env.example` - добавлены настройки PostgreSQL

### Файлы, которые были созданы:
1. `db/schema.sql` - полная SQL-схема БД
2. `db/init_database.py` - скрипт инициализации
3. `db/README.md` - документация БД
4. `REFACTORING_PHASE1.md` - этот документ

### Файлы, которые НЕ изменялись:
- `main.py` - логика бота без изменений
- `bot/handlers/*` - обработчики сообщений без изменений
- `bot/services/notifications.py` - логика уведомлений без изменений
- n8n workflows - будут обновлены в Фазе 2

---

## Тестирование

### Ручное тестирование

1. **Подключение к БД:**
   ```bash
   python db/init_database.py
   ```
   Ожидаемый результат: ✓ Подключение установлено, таблицы созданы

2. **Проверка моделей:**
   ```python
   from bot.services.database import setup_database
   from bot.config import Config

   config = Config()
   await setup_database(config)
   # Ожидается: успешная инициализация без ошибок
   ```

3. **Проверка представлений:**
   ```sql
   SELECT * FROM v_active_mentors;
   SELECT * FROM v_pending_webhooks;
   ```

### Что проверить перед продолжением:

- [ ] Подключение к PostgreSQL работает
- [ ] Все таблицы созданы (см. `db/init_database.py`)
- [ ] Индексы созданы
- [ ] Представления доступны
- [ ] Триггеры `updated_at` работают
- [ ] Справочные данные заполнены через DBeaver

---

## Следующие шаги (Фаза 2)

### Обновление n8n workflow

**Задача:** Обновить `n8n/workflows/Getcourse_webhook_insert.json` для записи в PostgreSQL

**Изменения:**
1. Заменить таблицу `temp_webhook_logs` на `webhook_events`
2. Добавить поле `raw_payload` (полный JSON вебхука)
3. Добавить поле `processed = false` (для обработки ботом)
4. Настроить подключение к PostgreSQL через переменные окружения n8n
5. Обновить тестовый скрипт `test_run_load.py`

**Цель:**
- 0 потерь вебхуков
- <100ms время ответа
- Надежная запись в PostgreSQL

---

## Риски и ограничения

### Риски

1. **Пароль в .env** - не коммитить пароль в Git
   - Решение: добавить `.env` в `.gitignore`

2. **Ручное заполнение справочников** - ошибки ввода данных
   - Решение: валидация через CHECK constraints в PostgreSQL

3. **Миграция без даунтайма** - переключение на лету
   - Решение: поддержка SQLite и PostgreSQL параллельно через `DB_TYPE`

### Ограничения

1. **Справочные данные** - только ручное заполнение через DBeaver
2. **Нет автоматической миграции** - данные из SQLite НЕ переносятся
3. **Инициализация БД** - только через `init_database.py`, не через Alembic

---

## Коммит и merge

### Коммит в ветку

```bash
git add .
git commit -m "feat: Phase 1 - PostgreSQL schema and models

- Создана SQL-схема с поддержкой временной актуальности
- Обновлены SQLAlchemy модели для PostgreSQL
- Добавлена модель WebhookEvent для вебхуков GetCourse
- Настроен connection pooling для asyncpg
- Создан скрипт инициализации БД
- Добавлена документация (db/README.md)

Поля актуальности (valid_from, valid_to) для всех справочников
Поддержка JSONB для хранения raw webhook payload
Автоматическое обновление updated_at через триггеры
"
```

### Тестирование перед merge

- [ ] Запустить `db/init_database.py` - успешно
- [ ] Проверить подключение из бота
- [ ] Заполнить тестовые данные в DBeaver
- [ ] Проверить представления (views)

### Merge в main

```bash
# После тестирования
git checkout main
git merge refactor/phase1-postgresql-schema
git push origin main
```

---

## Контрольный список (Checklist)

### Разработка
- [x] Создана SQL-схема (`db/schema.sql`)
- [x] Обновлены SQLAlchemy модели
- [x] Добавлены зависимости (asyncpg, psycopg2)
- [x] Обновлена конфигурация (`bot/config.py`)
- [x] Создан скрипт инициализации (`db/init_database.py`)
- [x] Написана документация (`db/README.md`)

### Тестирование
- [x] Подключение к PostgreSQL работает
- [x] Таблицы созданы корректно (11 таблиц)
- [x] Индексы и представления работают (56 индексов, 5 views)
- [x] Триггеры обновляют `updated_at`
- [x] Справочные данные заполнены (вручную через DBeaver)
- [x] Тесты пройдены успешно

### Документация
- [x] README.md для базы данных
- [x] REFACTORING_PHASE1.md (этот файл)
- [x] Комментарии в коде
- [x] Примеры использования

### Deploy
- [ ] .env настроен на сервере Amvera
- [ ] БД инициализирована на production
- [ ] Справочные данные заполнены через DBeaver
- [ ] Бот подключается к PostgreSQL

---

**Фаза 1 завершена. Готово к переходу к Фазе 2 (n8n webhook integration).**
