# Следующие шаги после Фазы 1

**Текущий статус:** ✅ Фаза 1 завершена (PostgreSQL Schema & Models)
**Текущая ветка:** `refactor/phase1-postgresql-schema`
**Дата:** 2025-12-20

---

## Что нужно сделать СЕЙЧАС

### 1. Инициализация базы данных на сервере

```bash
cd getcourse_bot

# Проверьте .env файл
cat .env | grep POSTGRES

# Запустите скрипт инициализации
python db/init_database.py
```

**Ожидаемый результат:**
```
✓ Подключение установлено
✓ Схема базы данных создана успешно

📊 Созданные таблицы (13):
  - mentors (10 столбцов)
  - students (8 столбцов)
  - trainings (9 столбцов)
  - lessons (12 столбцов)
  - mapping (9 столбцов)
  - webhook_events (16 столбцов)
  - notifications (10 столбцов)
  ...
```

### 2. Заполнение справочных данных через DBeaver

**Подключение к PostgreSQL:**
- Host: `getcoursebd-spiderdad.db-msk0.amvera.tech`
- Port: `5432`
- Database: `GetCourseBD`
- User: `postgresql`
- Password: (из .env файла)

**Таблицы для заполнения:**

#### 2.1. Таблица `mentors`
```sql
INSERT INTO mentors (mentor_id, email, first_name, last_name, telegram_id, valid_from, valid_to)
VALUES
  ('mentor1@example.com', 'Иван', 'Иванов', 123456789, NOW(), '9999-12-31'::TIMESTAMPTZ),
  ('mentor2@example.com', 'Петр', 'Петров', 987654321, NOW(), '9999-12-31'::TIMESTAMPTZ);
```

**Обязательные поля:**
- `mentor_id` - ID наставника в GetCourse
- `email` - уникальный email ментора
- `valid_from` - дата начала актуальности (обычно NOW())
- `valid_to` - дата окончания ('9999-12-31' для активных)

**Опциональные поля:**
- `telegram_id` - ID из Telegram (получается при регистрации в боте)
- `first_name`, `last_name`, `username` - для отображения

#### 2.2. Таблица `students`
```sql
INSERT INTO students (user_email, first_name, last_name, valid_from, valid_to)
VALUES
  ('student1@example.com', 'Анна', 'Смирнова', NOW(), '9999-12-31'::TIMESTAMPTZ),
  ('student2@example.com', 'Елена', 'Кузнецова', NOW(), '9999-12-31'::TIMESTAMPTZ);
```

#### 2.3. Таблица `trainings`
```sql
INSERT INTO trainings (training_id, title, start_date, end_date, valid_from, valid_to)
VALUES
  ('training-001', 'Тренинг №1', '2025-01-01'::TIMESTAMPTZ, '2025-06-30'::TIMESTAMPTZ, NOW(), '9999-12-31'::TIMESTAMPTZ);
```

#### 2.4. Таблица `lessons`
```sql
INSERT INTO lessons (lesson_id, training_id, module_number, lesson_number, title, opening_date, deadline_date, valid_from, valid_to)
VALUES
  ('lesson-001', 'training-001', 'M1', 1, 'Урок 1', '2025-01-05'::TIMESTAMPTZ, '2025-01-15'::TIMESTAMPTZ, NOW(), '9999-12-31'::TIMESTAMPTZ);
```

#### 2.5. Таблица `mapping`
```sql
-- Сначала получите ID из таблиц mentors и students
SELECT id, email FROM mentors;
SELECT id, user_email FROM students;

-- Затем создайте маппинг (замените 1 и 2 на реальные ID)
INSERT INTO mapping (student_id, mentor_id, training_id, assigned_date, valid_from, valid_to)
VALUES
  (1, 1, 'training-001', NOW(), NOW(), '9999-12-31'::TIMESTAMPTZ);
```

### 3. Проверка заполненных данных

```sql
-- Проверка активных менторов
SELECT * FROM v_active_mentors;

-- Проверка активных студентов
SELECT * FROM v_active_students;

-- Проверка маппинга с JOIN
SELECT * FROM v_active_mappings;

-- Статистика
SELECT
  (SELECT COUNT(*) FROM mentors WHERE valid_to = '9999-12-31'::TIMESTAMPTZ) as active_mentors,
  (SELECT COUNT(*) FROM students WHERE valid_to = '9999-12-31'::TIMESTAMPTZ) as active_students,
  (SELECT COUNT(*) FROM trainings WHERE valid_to = '9999-12-31'::TIMESTAMPTZ) as active_trainings,
  (SELECT COUNT(*) FROM lessons WHERE valid_to = '9999-12-31'::TIMESTAMPTZ) as active_lessons,
  (SELECT COUNT(*) FROM mapping WHERE valid_to = '9999-12-31'::TIMESTAMPTZ) as active_mappings;
```

### 4. Тестирование подключения бота

Создайте тестовый скрипт:

```python
# test_db_connection.py
import asyncio
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent))

from bot.config import Config
from bot.services.database import setup_database
from sqlalchemy import select, text

async def test_connection():
    """Тест подключения к PostgreSQL"""

    # Инициализация конфигурации
    config = Config()
    print(f"DB Type: {config.db_type}")
    print(f"DB URL: {config.db_url}")

    # Инициализация БД
    await setup_database(config)
    print("✓ База данных инициализирована")

    # Импорт моделей
    from bot.services.database import async_session, Mentor, Student, WebhookEvent

    # Тест 1: Простой запрос
    async with async_session() as session:
        result = await session.execute(text("SELECT 1 as test"))
        print(f"✓ Простой запрос: {result.scalar()}")

    # Тест 2: Получение менторов
    async with async_session() as session:
        result = await session.execute(select(Mentor))
        mentors = result.scalars().all()
        print(f"✓ Менторов в БД: {len(mentors)}")
        for m in mentors[:3]:
            print(f"  - {m.email} (TG: {m.telegram_id or 'не указан'})")

    # Тест 3: Получение студентов
    async with async_session() as session:
        result = await session.execute(select(Student))
        students = result.scalars().all()
        print(f"✓ Студентов в БД: {len(students)}")

    # Тест 4: Проверка вебхуков
    async with async_session() as session:
        result = await session.execute(
            select(WebhookEvent).where(WebhookEvent.processed == False)
        )
        webhooks = result.scalars().all()
        print(f"✓ Необработанных вебхуков: {len(webhooks)}")

    print("\n✅ Все тесты пройдены успешно!")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(test_connection())
```

Запуск:
```bash
python test_db_connection.py
```

---

## После успешного тестирования

### 5. Коммит изменений

```bash
git add .
git status

git commit -m "feat: Phase 1 - PostgreSQL schema and models

- Создана SQL-схема с поддержкой временной актуальности
- Обновлены SQLAlchemy модели для PostgreSQL
- Добавлена модель WebhookEvent для вебхуков GetCourse
- Настроен connection pooling для asyncpg
- Создан скрипт инициализации БД
- Добавлена документация

Справочные таблицы с полями valid_from/valid_to
Поддержка JSONB для raw webhook payload
Автоматическое обновление updated_at через триггеры
"
```

### 6. Переход к Фазе 2

**Задача Фазы 2:** Обновление n8n workflow для записи в PostgreSQL

**Что нужно сделать:**
1. Обновить `n8n/workflows/Getcourse_webhook_insert.json`:
   - Заменить таблицу на `webhook_events`
   - Добавить поле `raw_payload` (полный JSON)
   - Добавить поле `processed = false`

2. Настроить подключение PostgreSQL в n8n (переменные окружения)

3. Обновить тестовый скрипт `test_run_load.py`:
   - Проверка записи в PostgreSQL
   - Проверка поля `raw_payload`

4. Провести нагрузочное тестирование:
   - Цель: 0 потерь вебхуков
   - Цель: <100ms время ответа

**Создать ветку для Фазы 2:**
```bash
git checkout main
git checkout -b refactor
git merge refactor/phase1-postgresql-schema

git checkout -b refactor/phase2-n8n-webhooks
```

---

## Troubleshooting

### Проблема: "TimeoutError" при инициализации

**Причина:** Проблемы с подключением к PostgreSQL

**Решение:**
```powershell
# Проверьте .env
type .env | findstr POSTGRES

# Убедитесь, что имя пользователя правильное
POSTGRES_USER=postgresql  # НЕ postresql (без g)

# Проверьте доступность порта
Test-NetConnection -ComputerName getcoursebd-spiderdad.db-msk0.amvera.tech -Port 5432

# Убедитесь, что SERVER_ENV=dev
echo $env:SERVER_ENV
```

### Проблема: "Invalid password"

**Решение:**
```bash
# Проверьте пароль в .env
cat .env | grep POSTGRES_PASSWORD

# Убедитесь, что пароль правильный (без кавычек)
POSTGRES_PASSWORD=strongmanager
```

### Проблема: Таблицы не создаются

**Решение:**
```bash
# Пересоздайте таблицы вручную
psql -h getcoursebd-spiderdad.db-msk0.amvera.tech \
     -p 5432 \
     -U postgresql \
     -d GetCourseBD \
     -f db/schema.sql
```

---

## Контрольный список перед переходом к Фазе 2

- [x] БД инициализирована (`python db/init_database.py` выполнен успешно)
- [x] Справочные данные заполнены через DBeaver
- [x] Тестовое подключение из бота работает
- [x] Представления (views) доступны и работают
- [x] Триггеры `updated_at` обновляют дату
- [x] Все изменения закоммичены в ветку
- [x] Ветка протестирована локально
- [ ] Готов к merge в main (если требуется)

---

**После выполнения всех шагов переходите к Фазе 2!** 🚀
