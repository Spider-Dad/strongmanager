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

        self.db_path = self.data_dir / "getcourse_bot.db"

        # URL для базы данных
        self.db_url = f"sqlite+aiosqlite:///{self.db_path}"

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
