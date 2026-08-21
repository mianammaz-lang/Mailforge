from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import httpx
from database.database import get_db
from config.settings import settings
from services.settings_service import get_setting, set_setting

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/")
def view_settings(request: Request, db: Session = Depends(get_db)):
    mailforge_key = get_setting(db, "mailforge_api_key", settings.MAILFORGE_API_KEY)
    openrouter_key = get_setting(db, "openrouter_api_key", settings.OPENROUTER_API_KEY)
    openrouter_model = get_setting(db, "openrouter_model", settings.OPENROUTER_MODEL)
    scan_interval = get_setting(db, "scan_interval", "24")
    
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "mailforge_key": mailforge_key,
        "openrouter_key": openrouter_key,
        "openrouter_model": openrouter_model,
        "scan_interval": scan_interval,
        "active_page": "settings"
    })

@router.post("/save")
def save_settings(
    request: Request,
    mailforge_api_key: str = Form(None),
    openrouter_api_key: str = Form(None),
    openrouter_model: str = Form(None),
    scan_interval: str = Form(None),
    db: Session = Depends(get_db)
):
    if mailforge_api_key is not None:
        set_setting(db, "mailforge_api_key", mailforge_api_key.strip())
    if openrouter_api_key is not None:
        set_setting(db, "openrouter_api_key", openrouter_api_key.strip())
    if openrouter_model is not None:
        set_setting(db, "openrouter_model", openrouter_model.strip())
    if scan_interval is not None:
        set_setting(db, "scan_interval", scan_interval.strip())
        
    return RedirectResponse(url="/settings", status_code=303)

@router.get("/fetch-models")
async def fetch_models(api_key: str = None):
    # Fetch models from OpenRouter
    # Standard endpoint: https://openrouter.ai/api/v1/models
    # No auth actually required for getting models, but we can pass it if provided
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://openrouter.ai/api/v1/models", headers=headers)
            response.raise_for_status()
            data = response.json()
            models = data.get("data", [])
            # Filter for free models or just return all models that end with :free
            free_models = [m for m in models if m.get("id", "").endswith(":free")]
            # If no free models found (unlikely), return first 20 models
            if not free_models:
                free_models = models[:20]
            return {"status": "success", "models": free_models}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/providers")
def api_providers(request: Request, db: Session = Depends(get_db)):
    mailforge_key = get_setting(db, "mailforge_api_key", settings.MAILFORGE_API_KEY)
    intodns_key = get_setting(db, "intodns_api_key", settings.INTODNS_API_KEY)
    dnsxray_key = get_setting(db, "dnsxray_api_key", settings.DNSXRAY_API_KEY)
    emailprober_key = get_setting(db, "emailprober_api_key", settings.EMAILPROBER_API_KEY)
    openrouter_key = get_setting(db, "openrouter_api_key", settings.OPENROUTER_API_KEY)
    
    providers = {
        "Mailforge": "CONNECTED" if mailforge_key else "MISSING",
        "IntoDNS": "CONNECTED" if intodns_key else "MISSING",
        "DNSXray": "CONNECTED" if dnsxray_key else "MISSING",
        "EmailProber": "CONNECTED" if emailprober_key else "MISSING",
        "OpenRouter AI": "CONNECTED" if openrouter_key else "MISSING",
        "Local DNS": "ACTIVE"
    }
    return templates.TemplateResponse("api_providers.html", {
        "request": request,
        "providers": providers,
        "active_page": "providers"
    })
