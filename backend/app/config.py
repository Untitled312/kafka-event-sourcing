from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    DATABASE_URL: str
    KAFKA_BOOTSTRAP_SERVERS: str
    KAFKA_TOPIC: str = "audit_events"
    KAFKA_DLQ_TOPIC: str = "audit_dlq"
    JWT_SECRET_FILE: Path = Path("/run/secrets/jwt_secret")
    APP_ENV: str = "production"
    LOG_LEVEL: str = "INFO"

    @property
    def jwt_secret(self) -> bytes:
        return self.JWT_SECRET_FILE.read_bytes().strip()

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()