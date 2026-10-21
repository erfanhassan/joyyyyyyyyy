from typing import List, Union
import os
from pydantic import AnyHttpUrl, field_validator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App Settings
    PROJECT_NAME: str = "JOY"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    # CORS Origins
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "https://joy.sonictch.com",
        "http://joy.sonictch.com",
    ]

    # Database & Cache
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/joy"
    REDIS_URL: str = "redis://localhost:6379/0"

    # AI Reasoning & Embeddings
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    OPENAI_API_KEY: str = ""

    # Telephony & Voice (LiveKit + Bangladeshi SIP AmberIT / Telnyx)
    TELEPHONY_API_KEY: str = ""
    TELEPHONY_PHONE_NUMBER: str = ""
    LIVEKIT_URL: str = ""
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""
    LIVEKIT_STT_MODEL: str = "openai/whisper-1"
    LIVEKIT_LLM_MODEL: str = "deepseek-ai/deepseek-v3"
    LIVEKIT_TTS_MODEL: str = "openai/tts-1"
    OPENAI_VOICE: str = "alloy"
    SIP_TRUNK_PROVIDER: str = "AmberIT"
    AMBERIT_SIP_SERVER: str = ""
    AMBERIT_EXTENSION: str = ""
    AMBERIT_SIP_PASSWORD: str = ""
    AMBERIT_SIP_USER: str = ""
    AMBERIT_SIP_PHONE: str = ""
    AMBERIT_SWITCH_URI: str = ""
    AMBERIT_GATEWAY_URI: str = ""

    # Social Channels (Meta Graph API)
    META_APP_ID: str = ""
    META_APP_SECRET: str = ""
    META_VERIFY_TOKEN: str = "joy_meta_verify_token_default"

    # Storefront Integrations
    SHOPIFY_API_SECRET: str = ""
    WOOCOMMERCE_WEBHOOK_SECRET: str = ""

    # Auth & Security
    CLERK_SECRET_KEY: str = ""
    CLERK_PUBLISHABLE_KEY: str = ""
    JOY_INITIAL_ADMIN_EMAIL: str = ""
    ENCRYPTION_KEY_SECRET: str = Field(
        default_factory=lambda: os.environ.get("SESSION_SECRET", "")
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
