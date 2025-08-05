# Система логирования GetCourse Bot

## Обзор

Система логирования GetCourse Bot обеспечивает комплексное логирование с разделением на файлы и базу данных, автоматической ротацией и настраиваемыми уровнями логирования.

## Архитектура

### Компоненты системы

1. **Файловое логирование** - ежедневные файлы с ротацией
2. **Логирование в БД** - долгосрочное хранение всех логов
3. **Система алертов** - уведомления администраторов об ошибках
4. **Автоматическая очистка** - удаление старых логов

### Структура файлов

```
data/logs/
├── bot_20250803.log      # Обычные логи за 3 августа 2025
├── bot_20250804.log      # Обычные логи за 4 августа 2025
├── errors_20250803.log   # Ошибки за 3 августа 2025
└── errors_20250804.log   # Ошибки за 4 августа 2025
```

### Структура БД

#### Таблица `application_logs`
- `id` - первичный ключ
- `timestamp` - время записи
- `level` - уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `logger_name` - имя логгера
- `message` - сообщение
- `module` - модуль
- `function` - функция
- `line` - номер строки
- `created_at` - время создания записи

#### Таблица `error_logs`
- `id` - первичный ключ
- `timestamp` - время записи
- `level` - уровень логирования (WARNING, ERROR, CRITICAL)
- `logger_name` - имя логгера
- `message` - сообщение
- `traceback` - стек вызовов (для ошибок)
- `module` - модуль
- `function` - функция
- `line` - номер строки
- `created_at` - время создания записи

## Настройка

### Переменные окружения

```bash
# ===== НАСТРОЙКИ ЛОГИРОВАНИЯ =====

# Уровни логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_LEVEL=INFO          # Уровень для обычных логов
ERROR_LOG_LEVEL=WARNING # Уровень для файла ошибок

# Периоды хранения логов (в днях)
LOG_RETENTION_DAYS=7    # Файлы логов (dev: 7, prod: 30)
DB_LOG_RETENTION_DAYS=30 # Записи в БД (dev: 30, prod: 90)

# Интервал очистки старых логов (в часах)
LOG_CLEANUP_INTERVAL_HOURS=24
```

### Рекомендуемые настройки

#### Для разработки (dev)
```bash
LOG_LEVEL=DEBUG
ERROR_LOG_LEVEL=WARNING
LOG_RETENTION_DAYS=7
DB_LOG_RETENTION_DAYS=30
LOG_CLEANUP_INTERVAL_HOURS=24
```

#### Для продакшна (prod)
```bash
LOG_LEVEL=INFO
ERROR_LOG_LEVEL=WARNING
LOG_RETENTION_DAYS=30
DB_LOG_RETENTION_DAYS=90
LOG_CLEANUP_INTERVAL_HOURS=24
```

## Использование

### Базовое логирование

```python
import logging

logger = logging.getLogger(__name__)

# Разные уровни логирования
logger.debug("Отладочная информация")
logger.info("Информационное сообщение")
logger.warning("Предупреждение")
logger.error("Ошибка")
logger.critical("Критическая ошибка")
```

### Логирование с контекстом

```python
try:
    # Код, который может вызвать ошибку
    result = some_function()
    logger.info(f"Функция выполнена успешно: {result}")
except Exception as e:
    logger.error(f"Ошибка при выполнении функции: {e}", exc_info=True)
```

## Автоматическая очистка

### Файлы логов
- Удаляются файлы старше `LOG_RETENTION_DAYS` дней
- Очистка выполняется каждые `LOG_CLEANUP_INTERVAL_HOURS` часов
- Удаляются только файлы с именами `bot_YYYYMMDD.log` и `errors_YYYYMMDD.log`

### Записи в БД
- Удаляются записи старше `DB_LOG_RETENTION_DAYS` дней
- Очистка выполняется каждые `LOG_CLEANUP_INTERVAL_HOURS` часов
- Удаляются записи из обеих таблиц: `application_logs` и `error_logs`

## Мониторинг и алерты

### Система алертов
- Автоматические уведомления администраторов об ошибках
- Настройка через `ADMIN_IDS` в переменных окружения
- Отправка через Telegram бота

### Просмотр логов

#### Файлы
```bash
# Просмотр текущих логов
tail -f data/logs/bot_$(date +%Y%m%d).log
tail -f data/logs/errors_$(date +%Y%m%d).log

# Поиск ошибок
grep "ERROR" data/logs/errors_$(date +%Y%m%d).log
```

#### База данных
```sql
-- Последние ошибки
SELECT * FROM error_logs
ORDER BY timestamp DESC
LIMIT 10;

-- Ошибки за последний час
SELECT * FROM error_logs
WHERE timestamp > datetime('now', '-1 hour')
ORDER BY timestamp DESC;

-- Статистика по уровням логирования
SELECT level, COUNT(*) as count
FROM application_logs
WHERE timestamp > datetime('now', '-1 day')
GROUP BY level;
```

## Производительность

### Оптимизации
- Асинхронная запись в БД через очередь
- Батчевая запись (до 100 записей за раз)
- Неблокирующие операции
- Автоматическая очистка старых данных

### Мониторинг производительности
```sql
-- Размер таблиц логов
SELECT
    'application_logs' as table_name,
    COUNT(*) as record_count,
    COUNT(*) * 8 as estimated_size_kb
FROM application_logs
UNION ALL
SELECT
    'error_logs' as table_name,
    COUNT(*) as record_count,
    COUNT(*) * 8 as estimated_size_kb
FROM error_logs;
```

## Устранение неполадок

### Проблемы с записью в БД
- Проверьте подключение к БД
- Убедитесь, что таблицы созданы
- Проверьте права доступа

### Проблемы с файлами логов
- Проверьте права на запись в директорию `data/logs`
- Убедитесь, что достаточно места на диске
- Проверьте настройки ротации

### Высокое потребление памяти
- Уменьшите `LOG_CLEANUP_INTERVAL_HOURS`
- Уменьшите периоды хранения
- Проверьте размер очереди логов

## Миграция с старой системы

При обновлении с предыдущей версии:
1. Старые файлы `bot.log` остаются без изменений
2. Новые логи будут записываться в ежедневные файлы
3. Старые записи в таблице `logs` сохраняются
4. Новые логи записываются в `application_logs` и `error_logs`