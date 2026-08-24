import os
import sys
import logging

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from database.database import engine, Base
from routes import dashboard, domains, mailboxes, issues, history, settings, api

Base.metadata.create_all(bind=engine)

IS_VERCEL = os.environ.get("VERCEL") == "1" or os.environ.get("NOW_REGION") is not None

# No scheduler on Vercel — crons handle it
if not IS_VERCEL:
    from contextlib import asynccontextmanager
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()

    @asynccontextmanager
    async def lifespan(a: FastAPI):
        scheduler.start()
        yield
        scheduler.shutdown()

    app = FastAPI(title="Mailforge Infrastructure Health", lifespan=lifespan)
else:
    app = FastAPI(title="Mailforge Infrastructure Health")

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(dashboard.router)
app.include_router(domains.router, prefix="/domains")
app.include_router(mailboxes.router, prefix="/mailboxes")
app.include_router(issues.router, prefix="/issues")
app.include_router(history.router, prefix="/history")
app.include_router(settings.router, prefix="/settings")
app.include_router(api.router, prefix="/api")

@app.get("/api-providers")
def api_providers_redirect():
    return RedirectResponse(url="/settings/providers")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
