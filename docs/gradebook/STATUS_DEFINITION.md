### Статусы и правила категоризации (Gradebook)

Цель: единообразно рассчитывать статус по каждому студенту и уроку для короткой и информативной выдачи в Telegram.

Исходные данные
- Дедлайн: `lessons.deadline_date`.
- Ответы студента: берём первое (или самое раннее) событие из `logs` с `answer_lesson_id = lessons.id`.
- Время «сейчас»: серверное время при генерации отчёта.

Базовые статусы
- no_before_deadline — ответа нет и now < deadline (не сдал, дедлайн не прошёл)
- no_after_deadline — ответа нет и now ≥ deadline (не сдал, дедлайн прошёл)
- on_time — есть ответ и answer_date ≤ deadline (сдал вовремя)
- late — есть ответ и answer_date > deadline (сдал с опозданием)
- optional — необязательный урок без дедлайна (ответ не требуется)

Категории для агрегатов
- on_time_category: { on_time }
- not_on_time_category: { late, no_before_deadline, no_after_deadline }
  - Статус late относится к категории «не вовремя» и должен отображаться явно.

Правила вычисления статуса (последовательность)
1) Использовать дедлайн из `lessons.deadline_date`.
2) Найти earliest_answer_date — минимальную дату ответа из `logs` для данного `student_id` и `lesson_id`.
3) Если deadline отсутствует (урок без дедлайна):
   - Если earliest_answer_date отсутствует → optional
   - Иначе → on_time
4) Если deadline присутствует и earliest_answer_date отсутствует:
   - Если now < deadline → no_before_deadline
   - Иначе → no_after_deadline
5) Если deadline присутствует и earliest_answer_date присутствует:
   - Если earliest_answer_date ≤ deadline → on_time
   - Иначе → late

Состояния уроков и тренингов
- Урок:
  - not_started: `opening_date > now`
  - active: `opening_date <= now` и (`deadline_date` отсутствует или `deadline_date > now`)
  - completed: `deadline_date` присутствует и `deadline_date <= now`
- Тренинг:
  - not_started: `training.start_date > now` или все уроки not_started (fallback)
  - completed: `training.end_date <= now` или все уроки с дедлайнами completed (fallback)
  - active: иначе

Правила отображения по умолчанию
- В /progress и /progress_admin агрегаты считаются по активным и завершённым урокам/тренингам. not_started исключаются.
- В списках выбора показываем статусы, но блокируем выбор not_started (alert без применения фильтра).
