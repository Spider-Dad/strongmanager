# Руководство по тестированию Фазы 3

**Цель:** Проверка корректности работы всех Python-сервисов перед запуском в production

---

## Подготовка к тестированию

### 1. Настройка окружения

```bash
cd getcourse_bot

# Активация виртуального окружения
.\venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Установка зависимостей
pip install -r requirements.txt

# Проверка установки pytz
python -c "import pytz; print(pytz.__version__)"
```

### 2. Проверка конфигурации

```bash
# Создать .env для тестирования (если нет)
cp env.example .env

# Обязательные параметры для тестирования:
# DB_TYPE=postgresql
# SERVER_ENV=dev
# POSTGRES_HOST_EXTERNAL=getcoursebd-spiderdad.db-msk0.amvera.tech
# POSTGRES_USER=postgresql
# POSTGRES_PASSWORD=...
# POSTGRES_DB=GetCourseBD

# Проверка подключения к БД
python -c "from bot.config import Config; c = Config(); print(f'DB URL: {c.db_url}')"
```

### 3. Подготовка тестовых данных в PostgreSQL

**Через DBeaver:**

```sql
-- Создать тестового ментора
INSERT INTO mentors (mentor_id, email, first_name, last_name, telegram_id, valid_from, valid_to)
VALUES
  (99999, 'test_mentor@example.com', 'Test', 'Mentor', 123456789, NOW(), '9999-12-31'::TIMESTAMPTZ)
ON CONFLICT (email) DO NOTHING;

-- Создать тестового студента
INSERT INTO students (student_id, user_email, first_name, last_name, valid_from, valid_to)
VALUES
  (88888, 'test_student@example.com', 'Test', 'Student', NOW(), '9999-12-31'::TIMESTAMPTZ)
ON CONFLICT (student_id) DO NOTHING;

-- Создать тестовый тренинг
INSERT INTO trainings (training_id, title, start_date, end_date, valid_from, valid_to)
VALUES
  ('test-training-001', 'Тестовый тренинг', NOW(), NOW() + INTERVAL '6 months', NOW(), '9999-12-31'::TIMESTAMPTZ)
ON CONFLICT (training_id) DO NOTHING;

-- Создать тестовый урок с дедлайном через 24 часа
INSERT INTO lessons (lesson_id, training_id, module_number, lesson_number, lesson_title, deadline_date, valid_from, valid_to)
VALUES
  ('test-lesson-001', 'test-training-001', 1, 1, 'Тестовый урок', NOW() + INTERVAL '24 hours', NOW(), '9999-12-31'::TIMESTAMPTZ)
ON CONFLICT (lesson_id) DO NOTHING;

-- Создать mapping (используем id из таблиц!)
INSERT INTO mapping (student_id, mentor_id, training_id, assigned_date, valid_from, valid_to)
SELECT
  (SELECT id FROM students WHERE student_id = 88888),
  (SELECT id FROM mentors WHERE mentor_id = 99999),
  (SELECT id FROM trainings WHERE training_id = 'test-training-001'),
  NOW(),
  NOW(),
  '9999-12-31'::TIMESTAMPTZ
ON CONFLICT DO NOTHING;

-- Проверка
SELECT * FROM v_active_mappings WHERE student_email = 'test_student@example.com';
```

---

## Тестирование сервисов

### 1. Unit-тесты

#### 1.1. Тест NotificationCalculationService

```bash
python tests/test_notification_calculator.py
```

**Ожидаемый результат:**
```
✅ Тест форматирования ответа пройден
✅ Тест форматирования дедлайна пройден
✅ Тест форматирования напоминания пройден
✅ Тест конвертации временных зон пройден
```

**Что проверяется:**
- Формат сообщения о новом ответе (эмодзи, структура, ссылки)
- Формат сообщения о дедлайне (конвертация UTC → MSK)
- Формат напоминания
- Корректность конвертации временных зон

#### 1.2. Тест WebhookProcessor

```bash
python tests/test_webhook_processor.py
```

**Ожидаемый результат:**
```
✅ Формат сообщения корректен
```

**Что проверяется:**
- Форматирование сообщения о новом ответе
- Наличие всех обязательных элементов

#### 1.3. Тест DeadlineChecker

```bash
python tests/test_deadline_checker.py
```

**Ожидаемый результат:**
```
✅ Формат сообщения о дедлайне корректен
✅ Логика расчета приближающихся дедлайнов корректна
```

**Что проверяется:**
- Формат сообщения о дедлайне
- Логика определения приближающихся дедлайнов (36 часов)
- Конвертация UTC → Moscow TZ

---

### 2. Интеграционный тест

#### 2.1. Тест полного цикла обработки

```bash
python tests/test_phase3_integration.py
```

**Что происходит:**
1. Создается тестовый вебхук в `webhook_events`
2. Запускается `WebhookProcessingService.process_pending_webhooks()`
3. Проверяется создание уведомления
4. Проверяется обновление статуса вебхука

**Ожидаемый результат:**
```
Вебхук processed: True
Вебхук error: None
✅ Интеграционный тест завершен
```

**Если есть ошибки:**
- Проверьте наличие тестовых данных (см. раздел "Подготовка тестовых данных")
- Проверьте логи на наличие warning/error

#### 2.2. Ручной тест полного цикла

**Шаг 1: Создать тестовый вебхук**

```sql
INSERT INTO webhook_events (
  event_date, user_id, user_email, user_first_name, user_last_name,
  answer_id, answer_training_id, answer_lesson_id, answer_status,
  processed, created_at
)
VALUES (
  NOW(),
  88888,
  'test_student@example.com',
  'Test',
  'Student',
  77777,
  'test-training-001',
  'test-lesson-001',
  'new',
  false,
  NOW()
);

-- Запомнить ID
SELECT id FROM webhook_events ORDER BY id DESC LIMIT 1;
```

**Шаг 2: Запустить бота локально**

```bash
# В .env установить
SERVER_ENV=dev
DB_TYPE=postgresql

# Запустить
python main.py
```

**Шаг 3: Проверить логи (через 30 сек)**

```
INFO - Найдено 1 необработанных вебхуков
INFO - Создано уведомление для ментора 1 о новом ответе студента Test Student
INFO - Обработка завершена: успешно=1, ошибок=0
```

**Шаг 4: Проверить в БД**

```sql
-- Вебхук обработан?
SELECT id, processed, processed_at FROM webhook_events WHERE id = [ID];

-- Уведомление создано?
SELECT * FROM notifications ORDER BY id DESC LIMIT 1;
```

**Шаг 5: Проверить отправку (через 15 сек)**

```
INFO - Найдено 1 pending уведомлений
INFO - Уведомление [ID] отправлено ментору test_mentor@example.com (TG: 123456789)
INFO - Отправка завершена: отправлено=1, ошибок=0, без telegram_id=0
```

**Шаг 6: Проверить в Telegram**

Зайти в Telegram как тестовый ментор и проверить получение уведомления.

---

### 3. Тест проверки дедлайнов

**Шаг 1: Создать урок с дедлайном через 24 часа**

```sql
-- Уже создан в разделе "Подготовка тестовых данных"
SELECT * FROM lessons WHERE lesson_id = 'test-lesson-001';
```

**Шаг 2: Запустить проверку дедлайнов вручную**

```python
# В отдельном скрипте test_deadlines_manual.py
import asyncio
from bot.config import Config
from bot.services.database import setup_database
from bot.services.deadline_checker import DeadlineCheckService

async def main():
    config = Config()
    await setup_database(config)

    checker = DeadlineCheckService(config)
    await checker.check_deadlines()

    print("✅ Проверка завершена")

if __name__ == "__main__":
    asyncio.run(main())
```

```bash
python test_deadlines_manual.py
```

**Ожидаемый результат:**
```
INFO - Запуск проверки приближающихся дедлайнов
INFO - Найдено 1 уроков с приближающимися дедлайнами
INFO - Создано уведомление о дедлайне для ментора 1, студентов без ответов: 1
INFO - Проверка дедлайнов завершена. Создано уведомлений: 1
✅ Проверка завершена
```

**Шаг 3: Проверить в БД**

```sql
SELECT * FROM notifications
WHERE type = 'deadlineApproaching'
ORDER BY id DESC
LIMIT 1;
```

---

### 4. Тест напоминаний

**Шаг 1: Создать вебхук 2 дня назад**

```sql
INSERT INTO webhook_events (
  event_date, user_id, user_email, user_first_name, user_last_name,
  answer_id, answer_training_id, answer_lesson_id, answer_status,
  processed, created_at
)
VALUES (
  NOW() - INTERVAL '2 days',
  88888,
  'test_student@example.com',
  'Test',
  'Student',
  77778,
  'test-training-001',
  'test-lesson-001',
  'new',
  true,  -- Уже обработан
  NOW() - INTERVAL '2 days'
);
```

**Шаг 2: Запустить обработку напоминаний вручную**

```python
# test_reminders_manual.py
import asyncio
from datetime import datetime, timedelta
import pytz
from bot.config import Config
from bot.services.database import setup_database
from bot.services.reminder_service import ReminderService

async def main():
    config = Config()
    await setup_database(config)

    service = ReminderService(config)

    # Анализируем дату 2 дня назад
    analysis_date = datetime.now(pytz.UTC) - timedelta(days=2)
    await service.process_reminder_notifications(analysis_date)

    print("✅ Обработка напоминаний завершена")

if __name__ == "__main__":
    asyncio.run(main())
```

```bash
python test_reminders_manual.py
```

**Ожидаемый результат:**
```
INFO - Обработка напоминаний для даты: 2025-12-19
INFO - Найдено 1 ответов за 2025-12-19
INFO - Создано напоминание для наставника Test Mentor (1), студентов: 1
INFO - Обработка напоминаний завершена. Создано напоминаний: 1
✅ Обработка напоминаний завершена
```

---

### 5. Нагрузочное тестирование

#### 5.1. Создание множественных вебхуков

```python
# test_load_webhooks.py
import asyncio
from datetime import datetime
import pytz
from bot.config import Config
from bot.services.database import setup_database, get_session, WebhookEvent

async def create_test_webhooks(count=100):
    config = Config()
    await setup_database(config)

    async for session in get_session():
        for i in range(count):
            webhook = WebhookEvent(
                event_date=datetime.now(pytz.UTC),
                user_id=88888 + i,
                user_email=f'student{i}@test.com',
                user_first_name='Test',
                user_last_name=f'Student{i}',
                answer_id=77777 + i,
                answer_training_id='test-training-001',
                answer_lesson_id='test-lesson-001',
                answer_status='new',
                processed=False
            )
            session.add(webhook)

        await session.commit()
        print(f"✅ Создано {count} тестовых вебхуков")

if __name__ == "__main__":
    asyncio.run(create_test_webhooks(100))
```

```bash
python test_load_webhooks.py
```

#### 5.2. Проверка скорости обработки

```bash
# Запустить бота
python main.py

# В другом терминале смотреть логи
tail -f logs/bot.log | grep "Обработка завершена"

# Ожидается:
# Каждые 30 сек: "Обработка завершена: успешно=50, ошибок=0"
# Через ~1 минуту все 100 вебхуков обработаны
```

#### 5.3. Проверка результатов

```sql
-- Все ли вебхуки обработаны?
SELECT
  COUNT(*) as total,
  COUNT(*) FILTER (WHERE processed = true) as processed,
  COUNT(*) FILTER (WHERE processed = false) as pending,
  COUNT(*) FILTER (WHERE error_message IS NOT NULL) as errors
FROM webhook_events
WHERE created_at > NOW() - INTERVAL '1 hour';

-- Созданы ли уведомления?
SELECT COUNT(*) as total_notifications
FROM notifications
WHERE created_at > NOW() - INTERVAL '1 hour';
```

---

## Тестовые сценарии

### Сценарий 1: Новый ответ студента

**Шаги:**
1. Создать вебхук через n8n (или вручную в БД)
2. Подождать 30 секунд (обработка вебхуков)
3. Проверить создание уведомления в `notifications`
4. Подождать 15 секунд (отправка уведомлений)
5. Проверить получение сообщения в Telegram

**Проверки:**
- [ ] Вебхук обработан (`processed = true`)
- [ ] Уведомление создано (`type = answerToLesson`)
- [ ] Уведомление отправлено (`status = sent`)
- [ ] Сообщение получено в Telegram
- [ ] Формат сообщения корректный
- [ ] Ссылка на студента работает

### Сценарий 2: Приближающийся дедлайн

**Шаги:**
1. Создать урок с дедлайном через 24 часа
2. Создать студента без ответа на этот урок
3. Запустить `deadline_checker.check_deadlines()`
4. Проверить создание уведомления
5. Проверить отправку в Telegram

**Проверки:**
- [ ] Урок найден как "приближающийся дедлайн"
- [ ] Студент определен как "без ответа"
- [ ] Уведомление создано с корректным списком студентов
- [ ] Дата дедлайна сконвертирована в Moscow TZ
- [ ] Уведомление отправлено
- [ ] Формат сообщения корректный

### Сценарий 3: Напоминание о непроверенных ответах

**Шаги:**
1. Создать вебхук датой 2 дня назад
2. Запустить `reminder_service.process_reminder_notifications()`
3. Проверить создание напоминания
4. Проверить отправку в Telegram

**Проверки:**
- [ ] Ответ за целевую дату найден
- [ ] Ответ сгруппирован по наставнику
- [ ] Напоминание создано
- [ ] Время ответа сконвертировано в Moscow TZ
- [ ] Напоминание отправлено
- [ ] Формат сообщения корректный

### Сценарий 4: Регистрация нового ментора

**Шаги:**
1. Добавить ментора в БД БЕЗ telegram_id:
```sql
INSERT INTO mentors (mentor_id, email, first_name, last_name, valid_from, valid_to)
VALUES (99998, 'new_mentor@test.com', 'New', 'Mentor', NOW(), '9999-12-31'::TIMESTAMPTZ);
```

2. В Telegram отправить боту команду `/start`
3. Ввести email: `new_mentor@test.com`
4. Проверить обновление в БД

**Проверки:**
- [ ] Бот нашел ментора по email
- [ ] `telegram_id` обновлен в БД
- [ ] `username` обновлен в БД
- [ ] Приветственное сообщение получено
- [ ] Ментор может получать уведомления

### Сценарий 5: Дедупликация уведомлений

**Шаги:**
1. Запустить `deadline_checker.check_deadlines()` дважды подряд
2. Проверить что создано только одно уведомление

**Проверки:**
- [ ] При первом запуске уведомление создано
- [ ] При втором запуске дубликат обнаружен
- [ ] В логах: "Найден дубликат уведомления..."
- [ ] В БД только одно уведомление

---

## Проверка работы в production

### 1. Подготовка к деплою

**За неделю до запуска:**

```bash
# 1. Слить phase3 в refactoring
git checkout refactoring
git merge refactoring/phase3-business-logic

# 2. Провести финальное тестирование
python tests/test_phase3_integration.py

# 3. Обновить .env на Amvera (через веб-интерфейс)
# Добавить все новые переменные из env.example
```

**В день запуска:**

```bash
# 1. Слить refactoring в main
git checkout main
git merge refactoring

# 2. Push в репозиторий (автодеплой на Amvera)
git push origin main

# 3. Мониторинг логов на Amvera
# Через веб-интерфейс или SSH
```

### 2. Мониторинг первых часов

**Что проверять каждые 30 минут:**

1. **Логи бота:**
```bash
# Проверка что задачи запускаются
grep "Найдено.*необработанных вебхуков" logs/bot.log
grep "Найдено.*pending уведомлений" logs/bot.log
grep "Запуск проверки приближающихся дедлайнов" logs/bot.log
```

2. **PostgreSQL:**
```sql
-- Динамика обработки за последний час
SELECT
  COUNT(*) FILTER (WHERE processed = true) as processed,
  COUNT(*) FILTER (WHERE processed = false) as pending,
  COUNT(*) FILTER (WHERE error_message IS NOT NULL) as errors
FROM webhook_events
WHERE created_at > NOW() - INTERVAL '1 hour';

-- Статус уведомлений
SELECT
  status,
  COUNT(*) as count
FROM notifications
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY status;
```

3. **Telegram:**
- Попросить тестового ментора подтвердить получение уведомления
- Проверить корректность ссылок
- Проверить форматирование

### 3. Чеклист мониторинга

**Первые 24 часа:**

- [ ] Вебхуки обрабатываются (каждые 30 сек)
- [ ] Уведомления отправляются (каждые 15 сек)
- [ ] Дедлайны проверяются (каждый час)
- [ ] Нет критических ошибок в логах
- [ ] Менторы получают уведомления
- [ ] Формат сообщений корректный
- [ ] Ссылки работают
- [ ] Временные зоны корректны (дедлайны в MSK)

**Через 48 часов:**

- [ ] Напоминания отправились (в 12:00 MSK)
- [ ] Дубликаты не создаются
- [ ] Все типы уведомлений работают
- [ ] Нет накопления pending уведомлений
- [ ] Нет накопления необработанных вебхуков

---

## Откат в случае проблем

**Если что-то пошло не так:**

### Вариант 1: Быстрый фикс (мелкая проблема)

```bash
# Исправить код локально
# Закоммитить и push
git add .
git commit -m "fix: ..."
git push origin main

# Amvera автоматически задеплоит
```

### Вариант 2: Откат на предыдущую версию

```bash
# Откатить коммит
git revert HEAD
git push origin main

# Или откатить на конкретный коммит
git reset --hard [commit_hash_before_phase3]
git push origin main --force  # ТОЛЬКО если уверены!
```

### Вариант 3: Временное возвращение на GAS (критическая проблема)

**ВАЖНО:** Используется только в крайнем случае!

1. **Включить триггеры в Google Apps Script:**
```javascript
// Вручную через редактор GAS
setupTrigger();
setupTimedTrigger();
```

2. **Остановить бота на Amvera** (через веб-интерфейс)

3. **Исследовать проблему локально**

4. **Исправить и повторить деплой**

---

## Результаты тестирования

### Заполняется после прохождения всех тестов

**Дата тестирования:** _______

**Unit-тесты:**
- [ ] test_notification_calculator.py - ПРОЙДЕН / НЕ ПРОЙДЕН
- [ ] test_webhook_processor.py - ПРОЙДЕН / НЕ ПРОЙДЕН
- [ ] test_deadline_checker.py - ПРОЙДЕН / НЕ ПРОЙДЕН

**Интеграционные тесты:**
- [ ] test_phase3_integration.py - ПРОЙДЕН / НЕ ПРОЙДЕН
- [ ] Ручной тест полного цикла - ПРОЙДЕН / НЕ ПРОЙДЕН

**Функциональные тесты:**
- [ ] Сценарий 1: Новый ответ - ПРОЙДЕН / НЕ ПРОЙДЕН
- [ ] Сценарий 2: Дедлайн - ПРОЙДЕН / НЕ ПРОЙДЕН
- [ ] Сценарий 3: Напоминание - ПРОЙДЕН / НЕ ПРОЙДЕН
- [ ] Сценарий 4: Регистрация - ПРОЙДЕН / НЕ ПРОЙДЕН
- [ ] Сценарий 5: Дедупликация - ПРОЙДЕН / НЕ ПРОЙДЕН

**Обнаруженные проблемы:**
1. _________________________________________
2. _________________________________________

**Решения:**
1. _________________________________________
2. _________________________________________

---

**Тестирование завершено:** ДА / НЕТ

**Готовность к production:** ДА / НЕТ
