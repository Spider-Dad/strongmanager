### ERD (сущности и связи) для табеля

Существующие сущности (в БД бота):
- `mentors` (`Mentor`): id, telegram_id, email, first_name, last_name, username
- `students` (`Student`): id, user_email, first_name, last_name
- `mapping` (`Mapping`): id, student_id, mentor_id, training_id, assigned_date
- `trainings` (`Training`): id, title, is_active, progress_table_id
- `lessons` (`Lesson`): id, training_id, module_number, lesson_number, title, opening_date, deadline_date
- `logs` (`Log`): ... answer_training_id, answer_lesson_id, date, action, status и др.

Новые сущности:
- `progress_config`:
  - id (PK)
  - training_id (FK → trainings.id)
  - lesson_id (FK → lessons.id) [опционально]
  - deadline_override [опционально]
  - weight [опционально]
  - tags [опционально]
  - visibility [опционально]
- `progress_overrides`:
  - id (PK)
  - student_id (FK → students.id)
  - lesson_id (FK → lessons.id)
  - status_override (enum: on_time | late | no_before_deadline | no_after_deadline)
  - comment [опционально]
  - expires_at [опционально]

Связи (ключевые):
- `mapping.student_id` → `students.id`
- `mapping.mentor_id` → `mentors.id`
- `mapping.training_id` → `trainings.id`
- `lessons.training_id` → `trainings.id`
- `logs.answer_lesson_id` → `lessons.id`
- `progress_config.training_id` → `trainings.id`
- `progress_config.lesson_id` → `lessons.id`
- `progress_overrides.student_id` → `students.id`
- `progress_overrides.lesson_id` → `lessons.id`

Индексы (рекомендуется):
- `progress_config(training_id, lesson_id)`
- `progress_overrides(student_id, lesson_id)`
- `logs(answer_lesson_id, date)`
