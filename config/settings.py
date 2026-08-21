from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    MAILFORGE_API_KEY: Optional[str] = None
    INTODNS_API_KEY: Optional[str] = None
    DNSXRAY_API_KEY: Optional[str] = None
    EMAILPROBER_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: str = "meta-llama/llama-3.1-8b-instruct:free"
    
    DATABASE_URL: str = "sqlite:///./mailforge_health.db"
    SCAN_INTERVAL_HOURS: int = 24
    
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000

    class Config:
        env_file = ".env"

# Initialize settings
settings = Settings()

# Dynamically adjust DATABASE_URL for Vercel read-only filesystem compatibility
import os
if os.environ.get("VERCEL") == "1" or os.environ.get("NOW_REGION") is not None:
    if "sqlite" in settings.DATABASE_URL:
        settings.DATABASE_URL = "sqlite:////tmp/mailforge_health.db"

