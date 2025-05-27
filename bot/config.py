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
            self.data_dir = Path.cwd() / "data"

        self.db_path = self.data_dir / "getcourse_bot.db"

        # URL для базы данных
        self.db_url = f"sqlite+aiosqlite:///{self.db_path}"
