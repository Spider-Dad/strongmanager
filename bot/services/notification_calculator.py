"""
Сервис расчета и форматирования уведомлений

Отвечает за:
- Форматирование сообщений уведомлений
- Проверку дубликатов уведомлений
- Создание сигнатур для дедупликации
"""

import logging
import hashlib
from typing import Optional, List, Dict
from datetime import datetime

import pytz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.database import Notification

logger = logging.getLogger(__name__)


class NotificationCalculationService:
    """Сервис для расчета и валидации уведомлений"""

    def __init__(self, config):
        self.config = config
        self.moscow_tz = pytz.timezone('Europe/Moscow')

    async def check_duplicate_notification(
        self,
        session: AsyncSession,
        mentor_id: int,
        notification_type: str,
        lesson_title: Optional[str] = None,
        student_name: Optional[str] = None,
        deadline_date: Optional[datetime] = None
    ) -> bool:
        """
        Проверка дубликатов уведомлений

        Args:
            session: Сессия БД
            mentor_id: ID ментора
            notification_type: Тип уведомления
            lesson_title: Название урока (для дедлайнов)
            student_name: Имя студента (для дедлайнов)
            deadline_date: Дата дедлайна

        Returns:
            True если дубликат найден, False если нет
        """
        try:
            # Базовый запрос
            query = select(Notification).where(
                Notification.mentor_id == mentor_id,
                Notification.type == notification_type
            )

            # Для дедлайнов проверяем содержимое сообщения
            if notification_type == 'deadlineApproaching' and lesson_title and student_name and deadline_date:
                # Форматируем дату как в GAS (dd-MM-yyyy HH:mm)
                deadline_moscow = deadline_date.astimezone(self.moscow_tz)
                deadline_str = deadline_moscow.strftime('%d-%m-%Y %H:%M')

                # Ищем уведомление с такими же параметрами
                result = await session.execute(query)
                notifications = result.scalars().all()

                for notif in notifications:
                    # Проверяем наличие ключевых фраз в сообщении
                    if (student_name in notif.message and
                        lesson_title in notif.message and
                        deadline_str in notif.message):
                        logger.info(
                            f"Найден дубликат уведомления для ментора {mentor_id}: "
                            f"тип={notification_type}, урок={lesson_title}, студент={student_name}"
                        )
                        return True

            return False

        except Exception as e:
            logger.error(f"Ошибка при проверке дубликатов: {e}")
            # В случае ошибки считаем что дубликата нет (безопаснее отправить лишнее)
            return False

    def format_answer_notification(
        self,
        student_name: str,
        student_email: str,
        training_title: str,
        module_number: int,
        lesson_title: str,
        user_id: int
    ) -> str:
        """
        Форматирование сообщения о новом ответе на урок

        Соответствует формату из lessonHandlers.gs:81-92
        """
        answer_student_url = f"https://strongmanager.ru/teach/control/stat/userComments/id/{user_id}"

        message = (
            "🔔 *Новый ответ на урок!*\n\n"
            f"📚 *Тренинг:* {training_title}\n"
            f"📖 *Модуль:* {module_number}\n"
            f"📝 *Урок:* {lesson_title}\n\n"
            "✅ *Пожалуйста, оставь обратную связь в течение 3 дней, поставь напоминание!*\n\n"
            f"👤 *Студент:* {student_name} ({student_email})\n"
            f"➡️ [*Перейти к ответам студента*]({answer_student_url})"
        )

        return message

    def format_deadline_notification(
        self,
        training_title: str,
        module_number: int,
        lesson_title: str,
        deadline_date: datetime,
        students: List[Dict[str, str]]
    ) -> str:
        """
        Форматирование сообщения о приближающемся дедлайне

        Соответствует формату из deadlineHandlers.gs:152-163

        Args:
            training_title: Название тренинга
            module_number: Номер модуля
            lesson_title: Название урока
            deadline_date: Дата дедлайна (в UTC)
            students: Список студентов без ответов
        """
        # Конвертация в московское время
        deadline_moscow = deadline_date.astimezone(self.moscow_tz)
        deadline_str = deadline_moscow.strftime('%d-%m-%Y %H:%M')

        message = (
            f"⏰ *Срок ответа студента {deadline_str} (МСК)*\n\n"
            f"📚 *Тренинг:* {training_title}\n"
            f"📖 *Модуль:* {module_number}\n"
            f"📝 *Урок:* {lesson_title}\n\n"
            "✅ *Пожалуйста, свяжись со студентом и помоги ему, если есть сложности:*\n\n"
        )

        # Добавляем список студентов
        for student in students:
            first_name = student.get('first_name', '')
            last_name = student.get('last_name', '')
            email = student.get('email', '')
            message += f"👤 {first_name} {last_name} ({email})\n"

        return message

    def format_reminder_notification(
        self,
        students: List[Dict]
    ) -> str:
        """
        Форматирование сообщения-напоминания о непроверенных ответах

        Соответствует формату из reminderHandlers.gs:115-142

        Args:
            students: Список студентов с их ответами
        """
        message = (
            "⏰ *Напоминание!*\n\n"
            "*Просьба проверить, не осталось ли непроверенных ответов у следующих студентов.*\n\n"
            "*Возможно, вы уже проверили их, просто убедимся, что никто не упущен.*\n\n"
        )

        for student in students:
            first_name = student.get('first_name', '')
            last_name = student.get('last_name', '')
            user_id = student.get('user_id', '')
            webhook_date = student.get('webhook_date')

            student_name = f"{first_name} {last_name}"

            # Форматирование времени ответа
            answer_time = 'Время не указано'
            if webhook_date:
                try:
                    # Конвертация в московское время
                    if isinstance(webhook_date, str):
                        webhook_dt = datetime.fromisoformat(webhook_date.replace('Z', '+00:00'))
                    else:
                        webhook_dt = webhook_date

                    if webhook_dt.tzinfo is None:
                        webhook_dt = pytz.UTC.localize(webhook_dt)

                    webhook_moscow = webhook_dt.astimezone(self.moscow_tz)
                    answer_time = webhook_moscow.strftime('%d-%m-%Y %H:%M') + ' (МСК)'
                except Exception as e:
                    logger.warning(f"Ошибка форматирования даты для студента {student_name}: {e}")

            student_url = f"https://strongmanager.ru/teach/control/stat/userComments/id/{user_id}"

            message += (
                f"👤 *{student_name}*\n"
                f"Ответ: {answer_time}\n"
                f"➡️ [*Перейти к последним ответам студента*]({student_url})\n\n"
            )

        return message

    def calculate_message_signature(self, notification_data: Dict) -> str:
        """
        Создание хэша для дедупликации уведомлений

        Args:
            notification_data: Данные уведомления

        Returns:
            SHA256 хэш от ключевых полей
        """
        # Формируем строку из ключевых полей
        signature_parts = [
            str(notification_data.get('mentor_id', '')),
            str(notification_data.get('type', '')),
            str(notification_data.get('lesson_id', '')),
            str(notification_data.get('student_id', '')),
            str(notification_data.get('training_id', '')),
        ]

        signature_string = '|'.join(signature_parts)

        # Создаем SHA256 хэш
        return hashlib.sha256(signature_string.encode()).hexdigest()