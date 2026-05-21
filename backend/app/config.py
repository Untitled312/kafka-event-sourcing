from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    database_url_file: Optional[str] = None
    database_url: Optional[str] = None

    @property
    def get_database_url(self) -> str:
        if self.database_url_file and os.path.exists(self.database_url_file):
            with open(self.database_url_file, 'r') as f:
                return f.read().strip()
        if self.database_url:
            return self.database_url
        raise ValueError("DATABASE_URL not set and DATABASE_URL_FILE not found")

    kafka_bootstrap_servers: str = "kafka:29092"
    kafka_topic: str = "audit-events"

    log_level: str = "INFO"

    app_name: str = "Audit System Backend"
    debug: bool = False

    class Config:
        case_sensitive = False


settings = Settings()