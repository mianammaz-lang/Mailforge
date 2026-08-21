from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
import uvicorn
import logging
import sys
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database.database import engine, Base
from routes import dashboard, domains, mailboxes, issues, history, settings, api

# Configure logging to print to console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)

Base.metadata.create_all(bind=engine)

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(title="Mailforge Infrastructure Health", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(dashboard.router)
app.include_router(domains.router, prefix="/domains")
app.include_router(mailboxes.router, prefix="/mailboxes")
app.include_router(issues.router, prefix="/issues")
app.include_router(history.router, prefix="/history")
app.include_router(settings.router, prefix="/settings")
app.include_router(api.router, prefix="/api")

# Redirect /api-providers to /settings/providers for sidebar link
@app.get("/api-providers")
def api_providers_redirect():
    return RedirectResponse(url="/settings/providers")

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
