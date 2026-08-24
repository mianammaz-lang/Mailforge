from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    MAILFORGE_API_KEY: Optional[str] = None
    INSTANTLY_API_KEY: Optional[str] = None
    INTODNS_API_KEY: Optional[str] = None
    DNSXRAY_API_KEY: Optional[str] = None
    EMAILPROBER_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: str = "meta-llama/llama-3.1-8b-instruct:free"
    
    # Auth
    ADMIN_EMAIL: str = "Admin@alsharqi.co"
    ADMIN_PASSWORD: str = "ammaz@0346"
    SESSION_SECRET: str = "super-secret-default-key-change-in-production"
    CRON_SECRET: str = "default-cron-secret"
    
    # DB
    DATABASE_URL: str = "sqlite:///./mailforge_health.db"
    
    SCAN_INTERVAL_HOURS: int = 24
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000
    
    class Config:
        env_file = ".env"

settings = Settings()

# Do NOT silently switch to /tmp/ on Vercel unless explicitly requested
# In Vercel, the DATABASE_URL environment variable should point to a real Postgres DB.
if os.environ.get("VERCEL") == "1" and "sqlite" in settings.DATABASE_URL:
    # Fallback for preview deployments, but warns the user
    settings.DATABASE_URL = "sqlite:////tmp/mailforge_health.db"


