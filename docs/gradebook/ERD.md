### ERD (сущности и связи) для табеля

Существующие сущности (в БД бота):
- `mentors` (`Mentor`): id, telegram_id, email, first_name, last_name, username
- `students` (`Student`): id, user_email, first_name, last_name
- `mapping` (`Mapping`): id, student_id, mentor_id, training_id, assigned_date
- `trainings` (`Training`): id, title, is_active, progress_table_id
- `lessons` (`Lesson`): id, training_id, module_number, lesson_number, title, opening_date, deadline_date
- `logs` (`Log`): ... answer_training_id, answer_lesson_id, date, action, status и др.

Связи (ключевые):
- `mapping.student_id` → `students.id`
- `mapping.mentor_id` → `mentors.id`
- `mapping.training_id` → `trainings.id`
- `lessons.training_id` → `trainings.id`
- `logs.answer_lesson_id` → `lessons.id`

Индексы (рекомендуется):
- `logs(answer_lesson_id, date)`
