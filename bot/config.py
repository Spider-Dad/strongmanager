import os
from pathlib import Path

class Config:
    def __init__(self):
        # Основная конфигурация
        self.bot_token = os.getenv("BOT_TOKEN")
        self.api_url = os.getenv("API_URL", "https://script.google.com/macros/s/AKfycbw-UdIRL_Tw_xs59xQuFIZDPulSJYpt1dq5u0QNDa06qDSwML6KUfp9Elqy2yP81bhSPQ/exec")
        self.polling_interval = int(os.getenv("POLLING_INTERVAL", 15))
        self.env = os.getenv("SERVER_ENV", "dev")

        # Настройки webhook
        self.webhook_host = os.getenv("WEBHOOK_HOST", "")
        self.webhook_path = os.getenv("WEBHOOK_PATH", "/webhook")
        self.webhook_port = int(os.getenv("WEBHOOK_PORT", 8443))

        # Административные аккаунты
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        self.admin_ids = [int(admin_id.strip()) for admin_id in admin_ids_str.split(",") if admin_id.strip()]

        # Пути к данным
        if self.env == "prod":
            self.data_dir = Path("/data")
        else:
            # Корень проекта (папка getcourse_bot), независимо от текущей рабочей директории
            app_root = Path(__file__).resolve().parents[1]
            self.data_dir = app_root / "data"

        # ===== КОНФИГУРАЦИЯ БАЗЫ ДАННЫХ =====
        # Тип БД: postgresql или sqlite (для обратной совместимости)
        self.db_type = os.getenv("DB_TYPE", "postgresql").lower()

        if self.db_type == "postgresql":
            # PostgreSQL конфигурация
            # Определяем, используем ли внутреннее имя хоста Amvera или внешнее
            if self.env == "prod":
                # Prod: используем внутреннее доменное имя Amvera
                postgres_host = os.getenv("POSTGRES_HOST_INTERNAL", "amvera-spiderdad-cnpg-getcoursebd-rw")
            else:
                # Dev: используем внешний хост для доступа из интернета
                postgres_host = os.getenv("POSTGRES_HOST_EXTERNAL", "getcoursebd-spiderdad.db-msk0.amvera.tech")

            postgres_port = os.getenv("POSTGRES_PORT", "5432")
            postgres_user = os.getenv("POSTGRES_USER", "postgresql")
            postgres_password = os.getenv("POSTGRES_PASSWORD", "")
            postgres_db = os.getenv("POSTGRES_DB", "GetCourseBD")
            postgres_schema = os.getenv("POSTGRES_SCHEMA", "public")

            # Формируем URL для asyncpg
            self.db_url = (
                f"postgresql+asyncpg://{postgres_user}:{postgres_password}"
                f"@{postgres_host}:{postgres_port}/{postgres_db}"
            )

            # Параметры подключения для asyncpg
            self.db_connect_args = {
                "server_settings": {
                    "search_path": postgres_schema,
                    "timezone": "UTC"
                }
            }

            # Сохраняем параметры для использования в других модулях
            self.postgres_host = postgres_host
            self.postgres_port = postgres_port
            self.postgres_user = postgres_user
            self.postgres_db = postgres_db
            self.postgres_schema = postgres_schema

        else:
            # SQLite конфигурация (для обратной совместимости)
            self.db_path = self.data_dir / "getcourse_bot.db"
            self.db_url = f"sqlite+aiosqlite:///{self.db_path}"
            self.db_connect_args = {
                "timeout": 30.0,
            }

        # Google Sheets credentials
        # Если путь не указан явно, используем путь в папке data
        credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
        if credentials_path:
            # Для prod оставляем прежнее поведение
            if self.env == "prod":
                self.google_credentials_path = credentials_path
            else:
                # Для dev: относительные пути интерпретируем относительно data_dir
                p = Path(credentials_path)
                if p.is_absolute():
                    self.google_credentials_path = str(p)
                else:
                    self.google_credentials_path = str(self.data_dir / p.name)
        else:
            # Если не указан, используем файл в папке data (prod: /data)
            if self.env == "prod":
                self.google_credentials_path = "/data/central-insight-409215-196210033b14.json"
            else:
                self.google_credentials_path = str(self.data_dir / "central-insight-409215-196210033b14.json")

        self.google_spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID", "1HAq1DHBQH0xLthA-gvnBOg-0vpkDjaBsEOQxNx51WLo")

        # Настройки таймаутов и retry
        self.http_timeout = int(os.getenv("HTTP_TIMEOUT", 30))  # секунды
        self.http_connect_timeout = int(os.getenv("HTTP_CONNECT_TIMEOUT", 10))  # секунды
        self.max_retries = int(os.getenv("MAX_RETRIES", 3))
        self.retry_base_delay = float(os.getenv("RETRY_BASE_DELAY", 1.0))
        self.retry_max_delay = float(os.getenv("RETRY_MAX_DELAY", 60.0))

        # Настройки retry для уведомлений
        self.notification_max_retries = int(os.getenv("NOTIFICATION_MAX_RETRIES", 3))
        self.notification_retry_base_delay = float(os.getenv("NOTIFICATION_RETRY_BASE_DELAY", 2.0))
        self.notification_retry_max_delay = float(os.getenv("NOTIFICATION_RETRY_MAX_DELAY", 60.0))

        # Фича-флаги
        # Включение функционала табеля (по умолчанию выключен для безопасного релиза)
        self.gradebook_enabled = os.getenv("GRADEBOOK_ENABLED", "false").lower() == "true"

        # ===== НАСТРОЙКИ ОБРАБОТКИ ВЕБХУКОВ И УВЕДОМЛЕНИЙ =====
        # Интервалы обработки (в секундах/минутах)
        self.webhook_processing_interval = int(os.getenv("WEBHOOK_PROCESSING_INTERVAL", "30"))
        self.deadline_check_interval_minutes = int(os.getenv("DEADLINE_CHECK_INTERVAL_MINUTES", "60"))
        self.notification_send_interval = int(os.getenv("NOTIFICATION_SEND_INTERVAL", "15"))

        # Параметры дедлайнов
        self.deadline_warning_hours = int(os.getenv("DEADLINE_WARNING_HOURS", "36"))

        # Параметры напоминаний
        self.reminder_trigger_hour = int(os.getenv("REMINDER_TRIGGER_HOUR", "12"))
        self.reminder_analysis_days_back = int(os.getenv("REMINDER_ANALYSIS_DAYS_BACK", "2"))

        # Лимиты обработки
        self.webhook_batch_size = int(os.getenv("WEBHOOK_BATCH_SIZE", "50"))
        self.notification_batch_size = int(os.getenv("NOTIFICATION_BATCH_SIZE", "20"))