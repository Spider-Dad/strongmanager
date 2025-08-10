import os
import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Callable, Any, Optional, Type, Union, List
from functools import wraps

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Circuit Breaker для предотвращения каскадных сбоев"""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Выполняет функцию с проверкой состояния circuit breaker"""
        if self.state == "OPEN":
            if datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout):
                self.state = "HALF_OPEN"
            else:
                raise Exception("Circuit breaker is OPEN")

        try:
            result = func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = datetime.now()

            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"

            raise e


async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retry_exceptions: Union[Type[Exception], List[Type[Exception]]] = Exception,
    circuit_breaker: Optional[CircuitBreaker] = None
) -> Any:
    """
    Выполняет функцию с exponential backoff retry логикой

    Args:
        func: Функция для выполнения
        max_retries: Максимальное количество попыток
        base_delay: Базовая задержка в секундах
        max_delay: Максимальная задержка в секундах
        exponential_base: База для exponential backoff
        jitter: Добавлять ли случайность к задержке
        retry_exceptions: Исключения, при которых повторять попытку
        circuit_breaker: Circuit breaker для предотвращения каскадных сбоев

    Returns:
        Результат выполнения функции

    Raises:
        Последнее исключение после всех попыток
    """
    if isinstance(retry_exceptions, type):
        retry_exceptions = [retry_exceptions]

    last_exception = None

    # Длинная задержка при достижении лимита (429). Можно переопределить через окружение.
    rate_limit_backoff_seconds_env = os.getenv("RATE_LIMIT_BACKOFF_SECONDS")
    try:
        rate_limit_backoff_seconds = float(rate_limit_backoff_seconds_env) if rate_limit_backoff_seconds_env else 90.0
    except Exception:
        rate_limit_backoff_seconds = 90.0

    def _is_rate_limit_error(exc: Exception) -> bool:
        try:
            # gspread.exceptions.APIError или любой ответ, содержащий 429 / RATE_LIMIT_EXCEEDED / ReadRequestsPerMinutePerUser
            text = str(exc).lower()
            if "429" in text:
                return True
            if "rate_limit_exceeded" in text or "quota" in text and "exceeded" in text:
                return True
            # Попытка вытащить status_code из response, если есть
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code == 429:
                return True
        except Exception:
            pass
        return False

    for attempt in range(max_retries + 1):
        try:
            if circuit_breaker:
                return await circuit_breaker.call(func)
            else:
                return await func() if asyncio.iscoroutinefunction(func) else func()

        except Exception as e:
            last_exception = e

            # Проверяем, нужно ли повторять попытку
            should_retry = any(isinstance(e, exc_type) for exc_type in retry_exceptions)

            if not should_retry:
                logger.debug(f"Не повторяемое исключение: {type(e).__name__}: {e}")
                raise e

            if attempt == max_retries:
                logger.error(f"Превышено максимальное количество попыток ({max_retries})")
                raise e

            # Вычисляем задержку
            delay = min(base_delay * (exponential_base ** attempt), max_delay)

            # Специальная длинная задержка при 429 (RATE LIMIT)
            if _is_rate_limit_error(e):
                delay = max(delay, rate_limit_backoff_seconds)

            if jitter:
                delay = delay * (0.5 + random.random() * 0.5)

            logger.warning(f"Попытка {attempt + 1}/{max_retries + 1} не удалась: {e}. Повтор через {delay:.2f}с")

            if asyncio.iscoroutinefunction(func):
                await asyncio.sleep(delay)
            else:
                await asyncio.sleep(delay)

    raise last_exception


def retry_decorator(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retry_exceptions: Union[Type[Exception], List[Type[Exception]]] = Exception
):
    """
    Декоратор для добавления retry логики к функциям
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await retry_with_backoff(
                lambda: func(*args, **kwargs),
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                exponential_base=exponential_base,
                jitter=jitter,
                retry_exceptions=retry_exceptions
            )

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return retry_with_backoff(
                lambda: func(*args, **kwargs),
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                exponential_base=exponential_base,
                jitter=jitter,
                retry_exceptions=retry_exceptions
            )

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# Создаем глобальные circuit breakers для разных сервисов
sync_circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=300)  # 5 минут
api_circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=180)   # 3 минуты