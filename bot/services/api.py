import json
import logging
from typing import Dict, List, Optional, Union

import aiohttp

logger = logging.getLogger(__name__)

class ApiError(Exception):
    """Ошибка API Google Apps Script"""
    pass

async def make_api_request(api_url: str, action: str, params: Dict = None) -> Dict:
    """
    Выполняет запрос к API Google Apps Script.

    Args:
        api_url: URL API
        action: Тип действия (getNewNotifications, updateNotificationStatus, etc.)
        params: Дополнительные параметры запроса

    Returns:
        Dict: Ответ API

    Raises:
        ApiError: В случае ошибки API
    """
    if params is None:
        params = {}

    params["action"] = action

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, json=params) as response:
                if response.status != 200:
                    raise ApiError(f"Неверный статус ответа: {response.status}")

                response_data = await response.json()

                if not response_data.get("success", False):
                    raise ApiError(f"Ошибка API: {response_data.get('error', 'Неизвестная ошибка')}")

                return response_data
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка соединения с API: {e}")
        raise ApiError(f"Ошибка соединения с API: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка декодирования JSON: {e}")
        raise ApiError(f"Ошибка декодирования JSON: {e}")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при запросе к API: {e}")
        raise ApiError(f"Неизвестная ошибка при запросе к API: {e}")

async def get_new_notifications(api_url: str, limit: int = 10) -> List[Dict]:
    """
    Получает список новых уведомлений из Google Sheets.

    Args:
        api_url: URL API
        limit: Максимальное количество уведомлений

    Returns:
        List[Dict]: Список уведомлений
    """
    response = await make_api_request(api_url, "getNewNotifications", {"limit": limit})
    return response.get("notifications", [])

async def update_notification_status(api_url: str, notification_id: Union[str, int], status: str,
                                    telegram_message_id: Optional[int] = None) -> Dict:
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

    return await make_api_request(api_url, "updateNotificationStatus", params)

async def register_telegram_id(api_url: str, email: str, telegram_id: int,
                              telegram_username: Optional[str] = None) -> Dict:
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

    return await make_api_request(api_url, "registerTelegramId", params)

async def get_mentor_by_email(api_url: str, email: str) -> Optional[Dict]:
    """
    Получает информацию о менторе по email.

    Args:
        api_url: URL API
        email: Email ментора

    Returns:
        Optional[Dict]: Информация о менторе или None, если ментор не найден
    """
    try:
        response = await make_api_request(api_url, "getMentorByEmail", {"email": email})
        return response.get("mentor")
    except ApiError:
        return None
