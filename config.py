"""
Central configuration.
All settings load from environment variables (see .env.example).
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_ENV: str = "development"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

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
