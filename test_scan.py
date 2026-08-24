import asyncio
from database.database import SessionLocal
from services.scanner import HealthScanner
from config.settings import settings
import logging

logging.basicConfig(level=logging.INFO)

async def test_scan():
    db = SessionLocal()
    scanner = HealthScanner(db, settings, "test-manual-scan")
    await scanner.run_full_scan()
    print("Scan finished.")

if __name__ == "__main__":
    asyncio.run(test_scan())
