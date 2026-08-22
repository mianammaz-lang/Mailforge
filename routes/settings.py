from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import httpx
from database.database import get_db
from config.settings import settings
from services.settings_service import get_setting, set_setting
from services.instantly import InstantlyClient

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/")
def get_settings(request: Request, db: Session = Depends(get_db)):
    mailforge_api_key = get_setting(db, "mailforge_api_key") or settings.MAILFORGE_API_KEY
    instantly_api_key = get_setting(db, "instantly_api_key") or getattr(settings, "INSTANTLY_API_KEY", None)
    openrouter_api_key = get_setting(db, "openrouter_api_key") or settings.OPENROUTER_API_KEY
    openrouter_model = get_setting(db, "openrouter_model", "meta-llama/llama-3.1-8b-instruct:free")
    scan_interval = get_setting(db, "scan_interval", str(settings.SCAN_INTERVAL_HOURS))

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "active_page": "settings",
            "mailforge_api_key": mailforge_api_key,
            "instantly_api_key": instantly_api_key,
            "openrouter_api_key": openrouter_api_key,
            "openrouter_model": openrouter_model,
            "scan_interval": scan_interval,
        },
    )

@router.post("/save")
def save_settings(
    mailforge_api_key: str = Form(""),
    instantly_api_key: str = Form(""),
    openrouter_api_key: str = Form(""),
    openrouter_model: str = Form(""),
    scan_interval: str = Form(""),
    db: Session = Depends(get_db)
):
    set_setting(db, "mailforge_api_key", mailforge_api_key.strip())
    set_setting(db, "instantly_api_key", instantly_api_key.strip())
    set_setting(db, "openrouter_api_key", openrouter_api_key.strip())
    set_setting(db, "openrouter_model", openrouter_model.strip())
    set_setting(db, "scan_interval", scan_interval.strip())
    return RedirectResponse(url="/settings", status_code=303)

@router.post("/api-keys/delete")
def delete_api_key(key_name: str = Form(...), db: Session = Depends(get_db)):
    set_setting(db, key_name, "")
    return RedirectResponse(url="/settings/providers", status_code=303)

@router.get("/fetch-models")
async def fetch_models():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get("https://openrouter.ai/api/v1/models")
            response.raise_for_status()
            data = response.json()
            models = [
                {"id": m["id"], "name": m.get("name", m["id"])}
                for m in data.get("data", [])
                if m["id"].endswith(":free")
            ]
            return {"models": models}
    except Exception as e:
        return {"error": str(e), "models": []}

@router.get("/providers")
def get_providers(request: Request, db: Session = Depends(get_db)):
    mailforge_key = get_setting(db, "mailforge_api_key") or settings.MAILFORGE_API_KEY
    instantly_key = get_setting(db, "instantly_api_key") or getattr(settings, "INSTANTLY_API_KEY", None)
    openrouter_key = get_setting(db, "openrouter_api_key") or settings.OPENROUTER_API_KEY

    providers = {
        "Mailforge": {
            "key": "mailforge_api_key", 
            "status": "CONNECTED" if mailforge_key else "MISSING", 
            "icon": "bi-envelope-paper", 
            "color": "text-primary", 
            "description": "Domain and mailbox management"
        },
        "Instantly": {
            "key": "instantly_api_key", 
            "status": "CONNECTED" if instantly_key else "MISSING", 
            "icon": "bi-lightning-charge", 
            "color": "text-warning", 
            "description": "Inbox placement testing"
        },
        "OpenRouter AI": {
            "key": "openrouter_api_key", 
            "status": "CONNECTED" if openrouter_key else "MISSING", 
            "icon": "bi-robot", 
            "color": "text-success", 
            "description": "AI-powered recommendations"
        },
        "Local DNS": {
            "key": None, 
            "status": "ACTIVE", 
            "icon": "bi-hdd-network", 
            "color": "text-info", 
            "description": "SPF, DKIM, DMARC, DNSSEC checks"
        },
    }

    return templates.TemplateResponse(
        "api_providers.html",
        {
            "request": request,
            "active_page": "providers",
            "providers": providers
        }
    )

@router.get("/instantly/tests")
async def get_instantly_tests(db: Session = Depends(get_db)):
    instantly_api_key = get_setting(db, "instantly_api_key") or getattr(settings, "INSTANTLY_API_KEY", None)
    client = InstantlyClient(api_key=instantly_api_key)
    return await client.list_tests()

@router.get("/instantly/analytics")
async def get_instantly_analytics(db: Session = Depends(get_db)):
    instantly_api_key = get_setting(db, "instantly_api_key") or getattr(settings, "INSTANTLY_API_KEY", None)
    client = InstantlyClient(api_key=instantly_api_key)
    return await client.get_analytics()
