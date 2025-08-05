import json
import logging
import re
from typing import Dict, List, Optional, Union

import aiohttp
from bot.utils.retry import retry_with_backoff, api_circuit_breaker
from bot.config import Config

logger = logging.getLogger(__name__)

class ApiError(Exception):
    """Ошибка API Google Apps Script"""
    pass

class GoogleScriptError(Exception):
    """Ошибка Google Apps Script с HTML ответом"""
    def __init__(self, message: str, html_content: str = None, status_code: int = None):
        super().__init__(message)
        self.html_content = html_content
        self.status_code = status_code

def _extract_error_from_html(html_content: str) -> str:
    """
    Извлекает информацию об ошибке из HTML ответа Google Script

    Args:
        html_content: HTML содержимое ответа

    Returns:
        Извлеченная информация об ошибке
    """
    # Попытка найти стандартные сообщения об ошибках Google Script
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
            if error_text and len(error_text) > 10:  # Минимальная длина для осмысленного сообщения
                return error_text

    # Если не удалось извлечь конкретную ошибку, возвращаем общую информацию
    return f"Google Script вернул HTML вместо JSON (длина ответа: {len(html_content)} символов)"

async def _make_api_request_internal(api_url: str, action: str, params: Dict = None, config: Config = None) -> Dict:
    """
    Внутренняя функция для выполнения запроса к API с таймаутами
    """
    if params is None:
        params = {}

    params["action"] = action

    # Настройки таймаутов
    timeout = aiohttp.ClientTimeout(
        total=config.http_timeout if config else 30,
        connect=config.http_connect_timeout if config else 10
    )

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(api_url, json=params) as response:
            # Проверяем статус ответа
            if response.status != 200:
                # Пытаемся получить текст ответа для диагностики
                try:
                    response_text = await response.text()
                    logger.error(f"HTTP {response.status} от Google Script: {response_text[:500]}")
                    raise ApiError(f"Неверный статус ответа: {response.status}. Ответ: {response_text[:200]}")
                except Exception as e:
                    raise ApiError(f"Неверный статус ответа: {response.status}. Не удалось прочитать ответ: {e}")

            # Проверяем Content-Type
            content_type = response.headers.get('content-type', '').lower()

            if 'text/html' in content_type:
                # Google Script вернул HTML вместо JSON - это ошибка
                html_content = await response.text()
                error_message = _extract_error_from_html(html_content)

                logger.error(f"Google Script вернул HTML вместо JSON. Content-Type: {content_type}")
                logger.error(f"HTML ответ (первые 500 символов): {html_content[:500]}")

                raise GoogleScriptError(
                    f"Google Script вернул HTML вместо JSON: {error_message}",
                    html_content=html_content,
                    status_code=response.status
                )

            elif 'application/json' not in content_type and 'text/plain' not in content_type:
                # Неожиданный Content-Type
                logger.warning(f"Неожиданный Content-Type: {content_type}")

            # Пытаемся парсить JSON
            try:
                response_data = await response.json()
            except json.JSONDecodeError as e:
                # Если не удалось парсить JSON, получаем текст для диагностики
                response_text = await response.text()
                logger.error(f"Ошибка парсинга JSON: {e}")
                logger.error(f"Полученный ответ: {response_text[:500]}")
                raise ApiError(f"Ошибка парсинга JSON: {e}. Ответ: {response_text[:200]}")

            # Проверяем структуру ответа
            if not isinstance(response_data, dict):
                raise ApiError(f"Неожиданный формат ответа: ожидался dict, получен {type(response_data)}")

            if not response_data.get("success", False):
                error_msg = response_data.get('error', 'Неизвестная ошибка')
                logger.error(f"Google Script вернул ошибку: {error_msg}")
                raise ApiError(f"Ошибка API: {error_msg}")

            return response_data


async def make_api_request(api_url: str, action: str, params: Dict = None, config: Config = None) -> Dict:
    """
    Выполняет запрос к API Google Apps Script с retry логикой.

    Args:
        api_url: URL API
        action: Тип действия (getNewNotifications, updateNotificationStatus, etc.)
        params: Дополнительные параметры запроса
        config: Конфигурация для таймаутов и retry

    Returns:
        Dict: Ответ API

    Raises:
        ApiError: В случае ошибки API
    """
    max_retries = config.max_retries if config else 3
    base_delay = config.retry_base_delay if config else 1.0
    max_delay = config.retry_max_delay if config else 60.0

    return await retry_with_backoff(
        lambda: _make_api_request_internal(api_url, action, params, config),
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay,
        retry_exceptions=[aiohttp.ClientError, aiohttp.ServerTimeoutError, aiohttp.ClientOSError, GoogleScriptError],
        circuit_breaker=api_circuit_breaker
    )

async def get_new_notifications(api_url: str, limit: int = 10, config: Config = None) -> List[Dict]:
    """
    Получает список новых уведомлений из Google Sheets.

    Args:
        api_url: URL API
        limit: Максимальное количество уведомлений

    Returns:
        List[Dict]: Список уведомлений
    """
    response = await make_api_request(api_url, "getNewNotifications", {"limit": limit}, config)
    return response.get("notifications", [])

async def update_notification_status(api_url: str, notification_id: Union[str, int], status: str,
                                    telegram_message_id: Optional[int] = None, config: Config = None) -> Dict:
    """
    Обновляет статус уведомления в Google Sheets.

    Args:
        api_url: URL API
        notification_id: ID уведомления
        status: Новый статус (sent, failed, etc.)
        telegram_message_id: ID отправленного сообщения в Telegram

    Returns:
        Dict: Результат обновления
    """
    params = {
        "notificationId": notification_id,
        "status": status
    }

    if telegram_message_id:
        params["telegramMessageId"] = telegram_message_id

    return await make_api_request(api_url, "updateNotificationStatus", params, config)

async def register_telegram_id(api_url: str, email: str, telegram_id: int,
                              telegram_username: Optional[str] = None, config: Config = None) -> Dict:
    """
    Регистрирует Telegram ID ментора по email.

    Args:
        api_url: URL API
        email: Email ментора
        telegram_id: Telegram ID
        telegram_username: Username в Telegram

    Returns:
        Dict: Информация о менторе
    """
    params = {
        "email": email,
        "telegramId": telegram_id
    }

    if telegram_username:
        params["telegramUsername"] = telegram_username

    return await make_api_request(api_url, "registerTelegramId", params, config)

async def get_mentor_by_email(api_url: str, email: str, config: Config = None) -> Optional[Dict]:
    """
    Получает информацию о менторе по email.

    Args:
        api_url: URL API
        email: Email ментора

    Returns:
        Optional[Dict]: Информация о менторе или None, если ментор не найден
    """
    try:
        response = await make_api_request(api_url, "getMentorByEmail", {"email": email}, config)
        return response.get("mentor")
    except ApiError:
        return None
