import os
import sys
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from database.database import engine, Base, SessionLocal
from routes import dashboard, domains, mailboxes, issues, history, settings, api, auth
from services.auth import ensure_admin_exists, ALGORITHM
import jwt
from config.settings import settings as app_settings

Base.metadata.create_all(bind=engine)

IS_VERCEL = os.environ.get("VERCEL") == "1" or os.environ.get("NOW_REGION") is not None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure admin exists
    db = SessionLocal()
    ensure_admin_exists(db)
    db.close()
    
    if not IS_VERCEL:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.start()
        yield
        scheduler.shutdown()
    else:
        yield

app = FastAPI(title="Mailforge Infrastructure Health", lifespan=lifespan)

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        public_paths = ["/login", "/static", "/api/scan/cron"]
        if any(request.url.path.startswith(path) for path in public_paths) or request.url.path == "/favicon.ico":
            return await call_next(request)
            
        token = request.cookies.get("session_token")
        if not token:
            return RedirectResponse(url="/login", status_code=303)
            
        try:
            jwt.decode(token, app_settings.SESSION_SECRET, algorithms=[ALGORITHM])
        except Exception:
            return RedirectResponse(url="/login", status_code=303)
            
        return await call_next(request)

app.add_middleware(AuthMiddleware)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router)
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

