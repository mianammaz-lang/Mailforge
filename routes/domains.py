from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database.database import get_db
from database.models import Domain

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/")
def list_domains(request: Request, db: Session = Depends(get_db)):
    domains = db.query(Domain).all()
    return templates.TemplateResponse("domains.html", {
        "request": request,
        "domains": domains,
        "active_page": "domains"
    })

@router.get("/{domain_id}")
def domain_detail(request: Request, domain_id: int, db: Session = Depends(get_db)):
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    return templates.TemplateResponse("domain_detail.html", {
        "request": request,
        "domain": domain,
        "active_page": "domains"
    })
