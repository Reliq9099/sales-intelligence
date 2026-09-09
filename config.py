"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_title: str = os.getenv("BWC_APP_TITLE", "BWC Sales Intelligence")
    research_provider: str = os.getenv("BWC_RESEARCH_PROVIDER", "live").lower()
    request_timeout: int = int(os.getenv("BWC_REQUEST_TIMEOUT", "12"))
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


settings = Settings()