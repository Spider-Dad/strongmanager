# Система Retry-логики и обработки ошибок

**Версия: 1.2.0**

Документация по системе автоматических повторов и обработки сетевых ошибок в GetCourse Telegram Bot.

---

## Обзор

Система retry-логики обеспечивает надежную работу бота при временных сетевых проблемах и сбоях API. Включает в себя:

- **Exponential backoff** — автоматические повторы с увеличивающимися задержками
- **Circuit breaker** — предотвращение каскадных сбоев
- **Jitter** — случайность в задержках
- **Graceful degradation** — продолжение работы при проблемах

---

## Архитектура

### Основные компоненты

1. **`bot/utils/retry.py`** — основная утилита retry-логики
2. **`bot/config.py`** — конфигурация таймаутов и retry параметров
3. **`bot/services/api.py`** — API сервис с retry-логикой
4. **`bot/services/sync_service.py`** — сервис синхронизации с retry-логикой

### Circuit Breaker

Система использует два circuit breaker'а:

- **API Circuit Breaker** — для API запросов (5 попыток, восстановление через 3 минуты)
- **Sync Circuit Breaker** — для синхронизации (3 попытки, восстановление через 5 минут)

---

## Настройка

### Переменные окружения

#### HTTP таймауты
```bash
# Общий таймаут HTTP запросов (секунды)
HTTP_TIMEOUT=30

# Таймаут установки соединения (секунды)
HTTP_CONNECT_TIMEOUT=10
```

#### Retry для API запросов
```bash
# Максимальное количество попыток
MAX_RETRIES=3

# Базовая задержка между попытками (секунды)
RETRY_BASE_DELAY=1.0

# Максимальная задержка между попытками (секунды)
RETRY_MAX_DELAY=60.0
```

#### Retry для синхронизации
```bash
# Максимальное количество попыток для синхронизации
SYNC_MAX_RETRIES=3

# Базовая задержка для синхронизации (секунды)
SYNC_RETRY_BASE_DELAY=2.0

# Максимальная задержка для синхронизации (секунды)
SYNC_RETRY_MAX_DELAY=120.0
```

---

## Использование

### В API сервисе

```python
from bot.utils.retry import retry_with_backoff, api_circuit_breaker

# Автоматический retry с circuit breaker
result = await retry_with_backoff(
    lambda: make_api_request(url, action, params),
    max_retries=3,
    base_delay=1.0,
    max_delay=60.0,
    retry_exceptions=[aiohttp.ClientError, aiohttp.ServerTimeoutError],
    circuit_breaker=api_circuit_breaker
)
```

### В сервисе синхронизации

```python
from bot.utils.retry import retry_with_backoff, sync_circuit_breaker

# Retry для чтения Google Sheets
sheets_data = await retry_with_backoff(
    self._read_sheets_internal,
    max_retries=self.max_retries,
    base_delay=self.retry_base_delay,
    max_delay=self.retry_max_delay,
    retry_exceptions=[Exception],
    circuit_breaker=sync_circuit_breaker
)
```

### Декоратор для функций

```python
from bot.utils.retry import retry_decorator

@retry_decorator(max_retries=3, base_delay=1.0)
async def my_function():
    # Ваш код здесь
    pass
```

---

## Логирование

Система подробно логирует все попытки и ошибки:

```
2025-01-04 10:30:15 - bot.utils.retry - WARNING - Попытка 1/4 не удалась: Connection timeout. Повтор через 1.23с
2025-01-04 10:30:17 - bot.utils.retry - WARNING - Попытка 2/4 не удалась: Connection timeout. Повтор через 2.45с
2025-01-04 10:30:20 - bot.utils.retry - ERROR - Превышено максимальное количество попыток (3)
```

### Circuit Breaker состояния

```
2025-01-04 10:30:20 - bot.utils.retry - WARNING - Circuit breaker OPEN для API запросов
2025-01-04 10:33:20 - bot.utils.retry - INFO - Circuit breaker HALF_OPEN для API запросов
2025-01-04 10:33:21 - bot.utils.retry - INFO - Circuit breaker CLOSED для API запросов
```

---

## Мониторинг

### Статус Circuit Breaker

Можно проверить состояние circuit breaker'ов:

```python
from bot.utils.retry import api_circuit_breaker, sync_circuit_breaker

print(f"API Circuit Breaker: {api_circuit_breaker.state}")
print(f"Sync Circuit Breaker: {sync_circuit_breaker.state}")
```

### Метрики

Система предоставляет следующие метрики:

- Количество попыток для каждого запроса
- Время выполнения с учетом retry
- Состояние circuit breaker'ов
- Типы ошибок и их частота

---

## Рекомендации

### Для разработки

1. **Тестирование** — используйте `test_retry.py` для проверки retry-логики
2. **Логирование** — всегда проверяйте логи при проблемах с сетью
3. **Мониторинг** — следите за состоянием circuit breaker'ов

### Для продакшена

1. **Настройка таймаутов** — адаптируйте под вашу сетевую инфраструктуру
2. **Мониторинг алертов** — настройте алерты на частые retry
3. **Метрики** — отслеживайте эффективность retry-логики

### Оптимизация

1. **Увеличение задержек** — при частых сбоях увеличьте `RETRY_BASE_DELAY`
2. **Уменьшение попыток** — при стабильной сети уменьшите `MAX_RETRIES`
3. **Настройка circuit breaker** — адаптируйте пороги под ваши потребности

---

## Примеры конфигураций

### Для нестабильной сети
```bash
HTTP_TIMEOUT=60
HTTP_CONNECT_TIMEOUT=20
MAX_RETRIES=5
RETRY_BASE_DELAY=2.0
RETRY_MAX_DELAY=300.0
```

### Для стабильной сети
```bash
HTTP_TIMEOUT=15
HTTP_CONNECT_TIMEOUT=5
MAX_RETRIES=2
RETRY_BASE_DELAY=0.5
RETRY_MAX_DELAY=30.0
```

### Для синхронизации больших данных
```bash
SYNC_MAX_RETRIES=5
SYNC_RETRY_BASE_DELAY=5.0
SYNC_RETRY_MAX_DELAY=600.0
```