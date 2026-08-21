from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database.database import get_db
from database.models import Issue

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/")
def list_issues(request: Request, db: Session = Depends(get_db)):
    issues = db.query(Issue).order_by(Issue.detected_at.desc()).all()
    return templates.TemplateResponse("issues.html", {
        "request": request,
        "issues": issues,
        "active_page": "issues"
    })
