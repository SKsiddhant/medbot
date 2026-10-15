"""
Central configuration.
All settings load from environment variables (see .env.example).
"""
from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_ENV: str = "development"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = ""          # signs login tokens; REQUIRED when APP_ENV=production
    CORS_ORIGINS: str = "*"       # comma-separated list; restrict in production

    # Hugging Face
    HF_API_TOKEN: str = ""
    HF_NER_MODEL: str = "d4data/biomedical-ner-all"
    HF_DIALOGUE_MODEL: str = "epfl-llm/meditron-70b"
    USE_HF_INFERENCE_API: bool = True

    # Twilio (SMS is the primary channel)
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_SMS_FROM: str = ""
    TWILIO_WHATSAPP_FROM: str = "whatsapp:+14155238886"

    # Meta WhatsApp Cloud API
    META_WHATSAPP_TOKEN: str = ""
    META_PHONE_NUMBER_ID: str = ""
    META_VERIFY_TOKEN: str = "dev_verify_token"

    # DB
    DATABASE_URL: str = "sqlite:///./medbot.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalise_db_scheme(cls, v: str) -> str:
        # Render and Heroku hand out postgres://, which SQLAlchemy 2 rejects.
        return "postgresql://" + v[len("postgres://"):] if v.startswith("postgres://") else v

    # Doctor booking
    PRACTO_API_KEY: str = ""
    PRACTO_API_BASE: str = "https://api.practo.com"

    # Safety
    EMERGENCY_HELPLINE: str = "112"
    SUPPORT_EMAIL: str = "support@example.com"
    DISCLAIMER: str = (
        "SWASTHYA AI is an AI triage assistant, not a doctor. "
        "In an emergency call 112."
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
