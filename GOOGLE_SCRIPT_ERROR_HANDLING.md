# Обработка ошибок Google Apps Script

## Проблема

Google Apps Script может возвращать HTML страницы с ошибками вместо JSON ответов в следующих случаях:

1. **Ошибки выполнения скрипта** - синтаксические ошибки, ошибки логики
2. **Ошибки авторизации** - неверные ключи доступа
3. **Ошибки квот** - превышение лимитов Google Apps Script
4. **Ошибки сети** - проблемы с подключением к Google сервисам
5. **Ошибки развертывания** - неправильная настройка веб-приложения

## Решение

### 1. Проверка Content-Type

Добавлена проверка заголовка `Content-Type` в ответе:

```python
content_type = response.headers.get('content-type', '').lower()

if 'text/html' in content_type:
    # Google Script вернул HTML вместо JSON - это ошибка
    html_content = await response.text()
    error_message = _extract_error_from_html(html_content)
    raise GoogleScriptError(f"Google Script вернул HTML вместо JSON: {error_message}")
```

### 2. Извлечение ошибок из HTML

Реализована функция `_extract_error_from_html()` для извлечения полезной информации из HTML ответов:

```python
def _extract_error_from_html(html_content: str) -> str:
    error_patterns = [
        r'<title[^>]*>([^<]+)</title>',
        r'<h1[^>]*>([^<]+)</h1>',
        r'<div[^>]*class="error"[^>]*>([^<]+)</div>',
        r'<p[^>]*>([^<]+)</p>',
        r'<body[^>]*>([^<]+)</body>'
    ]

    for pattern in error_patterns:
        match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
        if match:
            error_text = match.group(1).strip()
            if error_text and len(error_text) > 10:
                return error_text

    return f"Google Script вернул HTML вместо JSON (длина ответа: {len(html_content)} символов)"
```

### 3. Новые типы исключений

#### GoogleScriptError
Исключение для ошибок Google Script с HTML ответом:

```python
class GoogleScriptError(Exception):
    def __init__(self, message: str, html_content: str = None, status_code: int = None):
        super().__init__(message)
        self.html_content = html_content
        self.status_code = status_code
```

#### ApiError
Улучшенное исключение для общих ошибок API с дополнительной диагностической информацией.

### 4. Улучшенное логирование

Добавлено детальное логирование для диагностики проблем:

```python
logger.error(f"Google Script вернул HTML вместо JSON. Content-Type: {content_type}")
logger.error(f"HTML ответ (первые 500 символов): {html_content[:500]}")
```

### 5. Retry логика

GoogleScriptError добавлен в список исключений для retry:

```python
retry_exceptions=[aiohttp.ClientError, aiohttp.ServerTimeoutError, aiohttp.ClientOSError, GoogleScriptError]
```

## Диагностика

### Команда диагностики

Добавлена команда `/alerts` → "🔍 Диагностика GScript" для проверки состояния Google Script.

### Тесты

Создан тестовый скрипт `test_gs_error_handling.py` для проверки:

1. Обработки некорректных URL
2. Обработки HTML ответов
3. Парсинга ошибок из HTML
4. Диагностики Google Script

## Использование

### В коде

```python
from bot.services.api import make_api_request, GoogleScriptError, ApiError

try:
    result = await make_api_request(api_url, "getNewNotifications", {"limit": 10})
except GoogleScriptError as e:
    logger.error(f"Ошибка Google Script: {e}")
    if e.html_content:
        logger.error(f"HTML ответ: {e.html_content[:500]}")
except ApiError as e:
    logger.error(f"Ошибка API: {e}")
```

### Через Telegram

1. Отправьте команду `/alerts` администратору
2. Выберите "🔍 Диагностика GScript"
3. Получите подробный отчет о состоянии Google Script

## Мониторинг

### Алерты

Все ошибки Google Script автоматически отправляются администраторам через систему алертов с детальной информацией:

- Тип ошибки (GoogleScriptError/ApiError)
- HTML содержимое ответа (если есть)
- Время возникновения
- Модуль, где произошла ошибка

### Логи

Детальные логи сохраняются для анализа:

```
ERROR - Google Script вернул HTML вместо JSON. Content-Type: text/html; charset=utf-8
ERROR - HTML ответ (первые 500 символов): <html><head><title>Google Apps Script Error</title>...
```

## Рекомендации

### Для разработчиков Google Script

1. **Обработка ошибок**: Добавьте try-catch блоки в Google Script
2. **Валидация параметров**: Проверяйте входящие параметры
3. **Логирование**: Используйте `Logger.log()` для отладки
4. **Квоты**: Следите за лимитами Google Apps Script

### Для администраторов бота

1. **Мониторинг**: Регулярно проверяйте алерты
2. **Диагностика**: Используйте команду диагностики при проблемах
3. **Логи**: Анализируйте логи для выявления паттернов ошибок
4. **Обновления**: Следите за обновлениями Google Apps Script

## Примеры ошибок

### Ошибка авторизации
```
Google Script вернул HTML вместо JSON: Access denied. Please check your credentials.
```

### Ошибка квот
```
Google Script вернул HTML вместо JSON: Quota exceeded for this script.
```

### Ошибка выполнения
```
Google Script вернул HTML вместо JSON: TypeError: Cannot read property 'getRange' of null
```

## Заключение

Новая система обработки ошибок Google Script обеспечивает:

- ✅ Надежное обнаружение HTML ответов
- ✅ Извлечение полезной информации об ошибках
- ✅ Детальное логирование для диагностики
- ✅ Автоматические алерты администраторам
- ✅ Retry логику для временных проблем
- ✅ Инструменты диагностики

Это значительно улучшает стабильность и отладку бота при работе с Google Apps Script.