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
    ABUSEIPDB_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: str = "meta-llama/llama-3.1-8b-instruct:free"
    
    # Auth
    ADMIN_EMAIL: str = "Admin@alsharqi.co"
    ADMIN_PASSWORD: str = "ammaz@0346"
    SESSION_SECRET: str = "super-secret-default-key-change-in-production"
    CRON_SECRET: str = "default-cron-secret"
    
    # DB - Hardcoded to Neon Postgres to ensure Vercel and Local use the exact same persistent database
    DATABASE_URL: str = "postgresql://neondb_owner:npg_2NbgMQ5JHXaw@ep-snowy-thunder-axdhquzw.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"
    
    SCAN_INTERVAL_HOURS: int = 24
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000
    
    class Config:
        env_file = ".env"

settings = Settings()


