from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database.database import get_db
from database.models import Mailbox

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/")
def list_mailboxes(request: Request, db: Session = Depends(get_db)):
    mailboxes = db.query(Mailbox).all()
    return templates.TemplateResponse("mailboxes.html", {
        "request": request,
        "mailboxes": mailboxes,
        "active_page": "mailboxes"
    })

@router.get("/{mailbox_id}")
def mailbox_detail(request: Request, mailbox_id: int, db: Session = Depends(get_db)):
    mailbox = db.query(Mailbox).filter(Mailbox.id == mailbox_id).first()
    return templates.TemplateResponse("mailbox_detail.html", {
        "request": request,
        "mailbox": mailbox,
        "active_page": "mailboxes"
    })
