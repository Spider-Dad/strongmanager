import asyncio
import logging
import aiohttp
from typing import Dict, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

class GoogleScriptDiagnostics:
    """Класс для диагностики проблем с Google Apps Script"""

    def __init__(self, api_url: str, config=None):
        self.api_url = api_url
        self.config = config

    async def test_connection(self) -> Dict:
        """
        Тестирует подключение к Google Script

        Returns:
            Dict с результатами тестирования
        """
        results = {
            "timestamp": datetime.now().isoformat(),
            "api_url": self.api_url,
            "tests": {}
        }

        # Тест 1: Проверка доступности URL
        results["tests"]["url_availability"] = await self._test_url_availability()

        # Тест 2: Проверка Content-Type
        results["tests"]["content_type"] = await self._test_content_type()

        # Тест 3: Проверка простого запроса
        results["tests"]["simple_request"] = await self._test_simple_request()

        # Тест 4: Проверка обработки ошибок
        results["tests"]["error_handling"] = await self._test_error_handling()

        return results

    async def _test_url_availability(self) -> Dict:
        """Тестирует доступность URL"""
        try:
            timeout = aiohttp.ClientTimeout(total=10, connect=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.api_url) as response:
                    return {
                        "status": "success",
                        "http_status": response.status,
                        "response_time": "OK",
                        "headers": dict(response.headers)
                    }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__
            }

    async def _test_content_type(self) -> Dict:
        """Тестирует Content-Type ответа"""
        try:
            timeout = aiohttp.ClientTimeout(total=10, connect=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.api_url, json={"action": "test"}) as response:
                    content_type = response.headers.get('content-type', '')
                    return {
                        "status": "success",
                        "content_type": content_type,
                        "is_html": 'text/html' in content_type.lower(),
                        "is_json": 'application/json' in content_type.lower(),
                        "http_status": response.status
                    }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__
            }

    async def _test_simple_request(self) -> Dict:
        """Тестирует простой запрос к API"""
        try:
            timeout = aiohttp.ClientTimeout(total=10, connect=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.api_url, json={"action": "getNewNotifications", "limit": 1}) as response:
                    content_type = response.headers.get('content-type', '')
                    response_text = await response.text()

                    return {
                        "status": "success",
                        "http_status": response.status,
                        "content_type": content_type,
                        "response_length": len(response_text),
                        "response_preview": response_text[:200],
                        "is_html_response": 'text/html' in content_type.lower()
                    }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__
            }

    async def _test_error_handling(self) -> Dict:
        """Тестирует обработку некорректных запросов"""
        try:
            timeout = aiohttp.ClientTimeout(total=10, connect=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Отправляем некорректный запрос
                async with session.post(self.api_url, json={"invalid": "request"}) as response:
                    content_type = response.headers.get('content-type', '')
                    response_text = await response.text()

                    return {
                        "status": "success",
                        "http_status": response.status,
                        "content_type": content_type,
                        "response_length": len(response_text),
                        "response_preview": response_text[:200],
                        "is_html_response": 'text/html' in content_type.lower()
                    }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__
            }

    def generate_report(self, results: Dict) -> str:
        """
        Генерирует отчет о диагностике

        Args:
            results: Результаты диагностики

        Returns:
            Отформатированный отчет
        """
        report = f"""
🔍 *ДИАГНОСТИКА GOOGLE SCRIPT*

📅 *Время:* {results['timestamp']}
🔗 *URL:* `{results['api_url']}`

"""

        for test_name, test_result in results["tests"].items():
            status_emoji = "✅" if test_result.get("status") == "success" else "❌"
            report += f"{status_emoji} *{test_name.upper()}:*\n"

            if test_result.get("status") == "success":
                for key, value in test_result.items():
                    if key != "status":
                        report += f"  • {key}: `{value}`\n"
            else:
                report += f"  • Ошибка: `{test_result.get('error', 'Неизвестная ошибка')}`\n"

            report += "\n"

        return report

async def run_diagnostics(api_url: str, config=None) -> str:
    """
    Запускает полную диагностику Google Script

    Args:
        api_url: URL Google Script
        config: Конфигурация

    Returns:
        Отчет о диагностике
    """
    diagnostics = GoogleScriptDiagnostics(api_url, config)
    results = await diagnostics.test_connection()
    return diagnostics.generate_report(results)