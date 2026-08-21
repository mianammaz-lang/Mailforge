from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database.database import get_db
from database.models import HealthSnapshot

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/")
def view_history(request: Request, db: Session = Depends(get_db)):
    snapshots = db.query(HealthSnapshot).order_by(HealthSnapshot.timestamp.desc()).limit(30).all()
    return templates.TemplateResponse("history.html", {
        "request": request,
        "snapshots": snapshots,
        "active_page": "history"
    })
