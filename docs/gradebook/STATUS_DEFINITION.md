### Статусы и правила категоризации (Gradebook)

Цель: единообразно рассчитывать статус по каждому студенту и уроку для короткой и информативной выдачи в Telegram.

Исходные данные
- Дедлайн: `lessons.deadline_date` (приоритетный источник), может быть переопределён через `progress_config.deadline_override`.
- Ответы студента: берём первое (или самое раннее) событие из `logs` с `answer_lesson_id = lessons.id`.
- Время «сейчас»: серверное время при генерации отчёта.
- Ручные корректировки: `progress_overrides` (накрывают вычисленный статус до момента `expires_at`).

Базовые статусы
- no_before_deadline — ответа нет и now < deadline (не сдал, дедлайн не прошёл)
- no_after_deadline — ответа нет и now ≥ deadline (не сдал, дедлайн прошёл)
- on_time — есть ответ и answer_date ≤ deadline (сдал вовремя)
- late — есть ответ и answer_date > deadline (сдал с опозданием)

Категории для агрегатов
- on_time_category: { on_time }
- not_on_time_category: { late, no_before_deadline, no_after_deadline }
  - Статус late относится к категории «не вовремя» и должен отображаться явно.

Правила вычисления статуса (последовательность)
1) Выбрать базовый дедлайн: `deadline = progress_config.deadline_override || lessons.deadline_date`.
2) Найти earliest_answer_date — минимальную дату ответа из `logs` для данного `student_id` и `lesson_id`.
3) Если earliest_answer_date отсутствует:
   - Если now < deadline → no_before_deadline
   - Иначе → no_after_deadline
4) Если earliest_answer_date присутствует:
   - Если earliest_answer_date ≤ deadline → on_time
   - Иначе → late
5) Применить override из `progress_overrides` (если есть актуальная запись): статус = `status_override`.

Опциональные расширения (не блокируют MVP)
- Веса уроков (`progress_config.weight`) для приоритезации при сортировке отстающих.
- Тэги уроков (`progress_config.tags`) для тематической фильтрации.
- Видимость урока (`progress_config.visibility`) для исключения из табеля.

Состояния уроков и тренингов
- Урок:
  - not_started: `opening_date > now`
  - active: `opening_date <= now < deadline_date`
  - completed: `deadline_date <= now`
- Тренинг (по множеству уроков):
  - not_started: все уроки not_started
  - completed: все уроки completed
  - active: иначе

Правила отображения по умолчанию
- В /progress и /progress_admin агрегаты считаются по активным и завершённым урокам/тренингам. not_started исключаются.
- В списках выбора показываем статусы, но блокируем выбор not_started (alert без применения фильтра).
