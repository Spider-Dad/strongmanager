# 📌 Следующие шаги после завершения Фазы 3

**Дата создания:** 2025-12-21
**Текущая ветка:** `refactoring/phase3-business-logic`

---

## ✅ Что уже сделано

- [x] Создано 5 новых Python-сервисов
- [x] Обновлена авторизация (PostgreSQL)
- [x] Обновлен main.py (APScheduler)
- [x] Обновлена конфигурация
- [x] Созданы тесты
- [x] Создана документация
- [x] Обновлен README в getcourse_apps_script (ARCHIVED)

---

## 🎯 Что нужно сделать СЕЙЧАС

### 1. Локальное тестирование

#### 1.1. Проверка временных зон

```powershell
cd getcourse_bot
.\venv\Scripts\activate

python tests\test_timezone_verification.py
```

**Ожидается:**
- ✅ PostgreSQL timezone: UTC
- ✅ Конвертация UTC → Moscow работает (+3 часа)
- ✅ Все проверки пройдены

#### 1.2. Unit-тесты

```powershell
python tests\test_notification_calculator.py
python tests\test_webhook_processor.py
python tests\test_deadline_checker.py
```

**Ожидается:**
- ✅ Формат всех сообщений корректен
- ✅ Конвертация временных зон работает

#### 1.3. Интеграционный тест (опционально)

**Требует:**
- Заполненные тестовые данные в PostgreSQL
- Подключение к БД

```powershell
python tests\test_manual_full_cycle.py
```

**Что произойдет:**
- Создаст тестовые данные (ментор, студент, тренинг, урок, mapping)
- Создаст и обработает тестовый вебхук
- Проверит создание уведомления
- Удалит тестовые данные

---

### 2. Проверка отсутствия зависимостей от GAS

```powershell
# В директории getcourse_bot

# Поиск упоминаний GAS API
findstr /s /i "api_url" bot\*.py
findstr /s /i "register_telegram_id" bot\*.py
findstr /s /i "get_new_notifications" bot\*.py
```

**Ожидается:**
- Только упоминания в комментариях или старых файлах
- Нет активного использования в коде

**Если найдены активные использования:**
- Проверить файлы и удалить/обновить импорты

---

### 3. Слияние веток

```powershell
# Проверить текущую ветку
git branch

# Должна быть: refactoring/phase3-business-logic

# Проверить статус
git status

# Если есть незакоммиченные файлы
git add .
git status

# Коммит
git commit -m "feat: Phase 3 - Business logic migration (GAS → Python)

- Создано 5 новых Python-сервисов для обработки вебхуков и уведомлений
- WebhookProcessingService - обработка вебхуков каждые 30 сек
- DeadlineCheckService - проверка дедлайнов каждый час
- ReminderService - напоминания раз в день (12:00 MSK)
- NotificationSenderService - отправка уведомлений каждые 15 сек
- NotificationCalculationService - форматирование и дедупликация

- Обновлена авторизация: удалены зависимости от GAS API
- Прямая работа с PostgreSQL таблицей mentors
- Проверка активных менторов через valid_to

- Обновлен main.py: 4 новые задачи APScheduler
- Обновлена конфигурация: 8 новых параметров
- Добавлен pytz для работы с временными зонами

- Создано тестирование: unit + интеграционное
- Создана полная документация (REFACTORING_PHASE3.md, PHASE3_TESTING_GUIDE.md)
- Обновлен README в getcourse_apps_script (пометка ARCHIVED)

Полная миграция логики из Google Apps Script в Python
Проект GAS готов к архивации
"

# Слить в refactoring
git checkout refactoring
git merge refactoring/phase3-business-logic

# Проверить
git log --oneline -5
```

---

## 🔜 Что нужно сделать ПЕРЕД production

### 1. Заполнение реальных данных в PostgreSQL

**Через DBeaver:**

#### Шаг 1: Менторы

```sql
-- Проверить текущее состояние
SELECT COUNT(*) FROM mentors WHERE valid_to = '9999-12-31'::TIMESTAMPTZ;

-- Добавить реальных менторов
-- telegram_id = NULL (заполнится после регистрации в боте!)
INSERT INTO mentors (mentor_id, email, first_name, last_name, valid_from, valid_to)
VALUES
  (..., '...@example.com', '...', '...', NOW(), '9999-12-31'::TIMESTAMPTZ);

-- Для старых менторов можно указать telegram_id сразу (из старой базы)
```

#### Шаг 2: Студенты

```sql
INSERT INTO students (student_id, user_email, first_name, last_name, valid_from, valid_to)
VALUES
  (...);
```

#### Шаг 3: Тренинги

```sql
INSERT INTO trainings (training_id, title, start_date, end_date, valid_from, valid_to)
VALUES
  ('...', '...', '2025-XX-XX'::TIMESTAMPTZ, '2025-XX-XX'::TIMESTAMPTZ, NOW(), '9999-12-31'::TIMESTAMPTZ);
```

#### Шаг 4: Уроки (с дедлайнами!)

```sql
INSERT INTO lessons (
  lesson_id, training_id, module_number, module_title,
  lesson_number, lesson_title, opening_date, deadline_date,
  valid_from, valid_to
)
VALUES
  ('...', '...', 1, 'Модуль 1', 1, 'Урок 1: ...',
   '2025-XX-XX'::TIMESTAMPTZ, '2025-XX-XX'::TIMESTAMPTZ,
   NOW(), '9999-12-31'::TIMESTAMPTZ);
```

#### Шаг 5: Mapping

```sql
-- ВАЖНО: Используем BIGINT id из таблиц, НЕ GetCourse ID!

-- Получить id
SELECT id, email FROM mentors WHERE mentor_id = ...;
SELECT id, user_email FROM students WHERE student_id = ...;
SELECT id, training_id FROM trainings WHERE training_id = '...';

-- Создать mapping
INSERT INTO mapping (student_id, mentor_id, training_id, assigned_date, valid_from, valid_to)
VALUES
  ([student.id], [mentor.id], [training.id], NOW(), NOW(), '9999-12-31'::TIMESTAMPTZ);
```

#### Проверка заполненных данных

```sql
-- Статистика
SELECT
  (SELECT COUNT(*) FROM mentors WHERE valid_to = '9999-12-31'::TIMESTAMPTZ) as mentors,
  (SELECT COUNT(*) FROM students WHERE valid_to = '9999-12-31'::TIMESTAMPTZ) as students,
  (SELECT COUNT(*) FROM trainings WHERE valid_to = '9999-12-31'::TIMESTAMPTZ) as trainings,
  (SELECT COUNT(*) FROM lessons WHERE valid_to = '9999-12-31'::TIMESTAMPTZ) as lessons,
  (SELECT COUNT(*) FROM mapping WHERE valid_to = '9999-12-31'::TIMESTAMPTZ) as mappings;

-- Проверка integrity
SELECT * FROM v_active_mappings LIMIT 10;

-- Уроки с дедлайнами
SELECT COUNT(*) as total, COUNT(deadline_date) as with_deadline
FROM lessons
WHERE valid_to = '9999-12-31'::TIMESTAMPTZ;
```

---

### 2. Обновление .env на Amvera

**Через веб-интерфейс Amvera:**

Добавить новые параметры:

```
WEBHOOK_PROCESSING_INTERVAL=30
DEADLINE_CHECK_INTERVAL_MINUTES=60
NOTIFICATION_SEND_INTERVAL=15
DEADLINE_WARNING_HOURS=36
REMINDER_TRIGGER_HOUR=12
REMINDER_ANALYSIS_DAYS_BACK=2
WEBHOOK_BATCH_SIZE=50
NOTIFICATION_BATCH_SIZE=20
```

Проверить существующие:

```
DB_TYPE=postgresql
SERVER_ENV=prod
POSTGRES_HOST_INTERNAL=amvera-spiderdad-cnpg-getcoursebd-rw
POSTGRES_USER=postgresql
POSTGRES_PASSWORD=strongmanager
POSTGRES_DB=GetCourseBD
```

---

### 3. Финальная проверка перед merge в main

```powershell
# На ветке refactoring
git checkout refactoring

# Проверить что все слито
git log --oneline --graph -10

# Финальный тест
python tests\test_manual_full_cycle.py

# Проверка отсутствия GAS зависимостей
findstr /s "api_url" bot\*.py
findstr /s "register_telegram_id" bot\*.py
```

---

### 4. Deploy в production

```powershell
# Когда готовы (с началом нового потока обучения)
git checkout main
git merge refactoring

# Проверка
git log --oneline -5
git status

# Push (автодеплой на Amvera)
git push origin main
```

---

### 5. Мониторинг после запуска

#### Первые 30 минут

```sql
-- Каждые 5 минут проверять
SELECT
  COUNT(*) FILTER (WHERE processed = false) as pending_webhooks,
  COUNT(*) FILTER (WHERE status = 'pending') as pending_notifications
FROM webhook_events, notifications;
```

#### Первые 24 часа

**Логи (каждый час):**
```bash
grep "Обработка завершена" logs/bot.log | tail -5
grep "Отправка завершена" logs/bot.log | tail -5
grep "ERROR" logs/error.log | tail -10
```

**PostgreSQL (каждый час):**
```sql
SELECT
  (SELECT COUNT(*) FROM webhook_events WHERE created_at > NOW() - INTERVAL '1 hour') as webhooks_last_hour,
  (SELECT COUNT(*) FROM notifications WHERE created_at > NOW() - INTERVAL '1 hour') as notifications_last_hour,
  (SELECT COUNT(*) FROM notifications WHERE sent_at > NOW() - INTERVAL '1 hour') as sent_last_hour;
```

---

### 6. Архивация GAS (после 48 часов)

**Когда система работает стабильно:**

1. **Отключить триггеры в Google Apps Script:**
```javascript
// Запустить в редакторе GAS
disableAllTriggers();
```

2. **Сохранить архивную копию:**
   - Создать копию проекта Apps Script
   - Сохранить на Google Drive: "Archive - GetCourse Apps Script (до 2025-12-21)"

3. **Создать Git тег:**
```powershell
cd getcourse_apps_script
git tag -a v1.0.0-archived -m "Архивная версия перед миграцией на Python"
git push origin v1.0.0-archived
```

---

## 📚 Полезные ссылки

### Документация

- **Фаза 3 (полная):** `wiki/REFACTORING_PHASE3.md`
- **Фаза 3 (резюме):** `wiki/PHASE3_COMPLETE.md`
- **Тестирование:** `wiki/PHASE3_TESTING_GUIDE.md`
- **Итоги рефакторинга:** `wiki/REFACTORING_COMPLETE.md`
- **Быстрый старт:** `QUICK_START_PHASE3.md`

### Предыдущие фазы

- **Фаза 1:** `wiki/REFACTORING_PHASE1.md`, `wiki/PHASE1_COMPLETE.md`
- **Фаза 2:** `wiki/REFACTORING_PHASE2.md`, `wiki/PHASE2_COMPLETE.md`

### Тесты

- `tests/test_timezone_verification.py` - проверка временных зон
- `tests/test_notification_calculator.py` - форматирование
- `tests/test_manual_full_cycle.py` - полный цикл (главный!)

---

## ⚠️ Важные напоминания

1. **Данные НЕ мигрируются из GAS** - все заполняется вручную в PostgreSQL
2. **telegram_id = NULL для новых менторов** - заполнится после регистрации
3. **GAS и Python НЕ работают параллельно** - либо одно, либо другое
4. **Временные зоны:** БД в UTC, отображение в Moscow TZ
5. **Бот сейчас отключен** - нет риска потери данных при запуске

---

## 📞 Если что-то пошло не так

### Проблема с тестами

См. `wiki/PHASE3_TESTING_GUIDE.md` раздел Troubleshooting

### Проблема с временными зонами

Запустить: `python tests/test_timezone_verification.py`

### Проблема с PostgreSQL

Проверить подключение:
```powershell
python -c "from bot.config import Config; from bot.services.database import setup_database; import asyncio; asyncio.run(setup_database(Config()))"
```

### Проблема при запуске бота

Проверить логи:
```powershell
python main.py 2>&1 | Tee-Object -FilePath startup_log.txt
```

---

## 🎉 Готово!

**Фаза 3 полностью завершена.**

**Следующий шаг:** Локальное тестирование (см. раздел выше)

**Когда будете готовы к production:**
1. Заполнить реальные данные в PostgreSQL
2. Обновить .env на Amvera
3. Слить в main и задеплоить
4. Мониторинг первых часов
5. Архивация GAS

---

**Удачи! 🚀**
