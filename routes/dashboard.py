from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database.database import get_db
from database.models import Domain, Mailbox, Issue, HealthSnapshot

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/")
@router.get("/dashboard")
def read_dashboard(request: Request, db: Session = Depends(get_db)):
    total_domains = db.query(Domain).count()
    healthy_domains = db.query(Domain).filter(Domain.status == 'HEALTHY').count()
    warning_domains = db.query(Domain).filter(Domain.status == 'WARNING').count()
    critical_domains = db.query(Domain).filter(Domain.status == 'CRITICAL').count()
    good_domains = db.query(Domain).filter(Domain.status == 'GOOD').count()
    
    total_mailboxes = db.query(Mailbox).count()
    healthy_mailboxes = db.query(Mailbox).filter(Mailbox.status == 'HEALTHY').count()
    warning_mailboxes = db.query(Mailbox).filter(Mailbox.status == 'WARNING').count()
    critical_mailboxes = db.query(Mailbox).filter(Mailbox.status == 'CRITICAL').count()
    good_mailboxes = db.query(Mailbox).filter(Mailbox.status == 'GOOD').count()
    campaign_ready = db.query(Mailbox).filter(Mailbox.campaign_ready == True).count()
    
    critical_issues = db.query(Issue).filter(Issue.severity == 'CRITICAL', Issue.status == 'OPEN').count()
    
    snapshot = db.query(HealthSnapshot).order_by(HealthSnapshot.timestamp.desc()).first()
    overall_health = snapshot.overall_score if snapshot else 0.0

    from database.models import InstantlyTest
    instantly_test = db.query(InstantlyTest).order_by(InstantlyTest.created_at.desc()).first()

    domains = db.query(Domain).limit(10).all()
    mailboxes = db.query(Mailbox).limit(10).all()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "total_domains": total_domains,
        "healthy_domains": healthy_domains,
        "warning_domains": warning_domains,
        "critical_domains": critical_domains,
        "good_domains": good_domains,
        "total_mailboxes": total_mailboxes,
        "healthy_mailboxes": healthy_mailboxes,
        "warning_mailboxes": warning_mailboxes,
        "critical_mailboxes": critical_mailboxes,
        "good_mailboxes": good_mailboxes,
        "campaign_ready": campaign_ready,
        "critical_issues": critical_issues,
        "overall_health": round(overall_health, 1),
        "instantly_test": instantly_test,
        "domains": domains,
        "mailboxes": mailboxes,
        "active_page": "dashboard"
    })
