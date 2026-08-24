from fastapi import APIRouter, Depends, Response, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io
import json
from datetime import datetime

from database.database import get_db
from database.models import Domain, Mailbox, Issue
from config.settings import settings

router = APIRouter()

import uuid
from fastapi import BackgroundTasks
from database.models import ScanRun

async def run_scan_in_background(scan_id: str, db_generator):
    db = next(db_generator())
    scan_run = db.query(ScanRun).filter(ScanRun.id == scan_id).first()
    if not scan_run:
        db.close()
        return

    from services.scanner import HealthScanner
    try:
        scan_run.status = "RUNNING"
        scan_run.progress = 10
        scan_run.current_stage = "Initializing"
        db.commit()

        scanner = HealthScanner(db, settings, scan_id)
        await scanner.run_full_scan()

        scan_run.status = "COMPLETED"
        scan_run.progress = 100
        scan_run.current_stage = "Completed"
        scan_run.completed_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        scan_run.status = "FAILED"
        scan_run.error_message = str(e)
        scan_run.completed_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()

@router.get("/api/domain/{domain_id}/reputation")
async def get_domain_reputation(domain_id: int, db: Session = Depends(get_db)):
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain or not domain.checks:
        return {"error": "Domain not found or no checks available"}
    check = domain.checks[-1]
    return {
        "domain": domain.name,
        "resolution": {
            "resolved_ips": check.resolved_ips or []
        },
        "blacklist": check.blacklist_details or {},
        "ip_reputation": check.ip_reputation or [],
        "overall_status": check.blacklist_status,
        "scan_timestamp": check.timestamp.isoformat()
    }

@router.post("/scan/instantly")
async def scan_instantly(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    scan_id = str(uuid.uuid4())
    run = ScanRun(id=scan_id, status="QUEUED", current_stage="Initialized")
    db.add(run)
    db.commit()
    
    async def run_task():
        from services.scanner import MailforgeScanner
        scanner = MailforgeScanner(db, scan_id)
        try:
            await scanner.run_instantly_checks()
        except Exception as e:
            pass
            
    background_tasks.add_task(run_task)
    return {"status": "success", "message": "Instantly Inbox test syncing", "scan_id": scan_id}

@router.post("/scan/full")
async def trigger_full_scan(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    scan_id = str(uuid.uuid4())
    scan_run = ScanRun(id=scan_id, status="QUEUED", progress=0, current_stage="Queued")
    db.add(scan_run)
    db.commit()

    background_tasks.add_task(run_scan_in_background, scan_id, get_db)
    
    return {"status": "success", "scan_id": scan_id}

@router.post("/scan/cron")
async def trigger_cron_scan(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    auth_header = request.headers.get("Authorization")
    cron_secret = getattr(settings, "CRON_SECRET", "default-cron-secret")
    
    if auth_header != f"Bearer {cron_secret}":
        return {"status": "error", "message": "Unauthorized"}
        
    scan_id = str(uuid.uuid4())
    scan_run = ScanRun(id=scan_id, status="QUEUED", progress=0, current_stage="Queued", environment="cron")
    db.add(scan_run)
    db.commit()

    background_tasks.add_task(run_scan_in_background, scan_id, get_db)
    return {"status": "success", "scan_id": scan_id}

@router.get("/scan/status/{scan_id}")
def get_scan_status(scan_id: str, db: Session = Depends(get_db)):
    scan_run = db.query(ScanRun).filter(ScanRun.id == scan_id).first()
    if not scan_run:
        return {"status": "error", "message": "Scan ID not found"}
        
    return {
        "scan_id": scan_run.id,
        "status": scan_run.status,
        "progress": scan_run.progress,
        "current_stage": scan_run.current_stage,
        "started_at": scan_run.started_at,
        "completed_at": scan_run.completed_at,
        "error": scan_run.error_message
    }


# EXPORTS

@router.get("/export/csv")
def export_csv(db: Session = Depends(get_db)):
    import pandas as pd
    domains = db.query(Domain).all()
    data = []
    for d in domains:
        data.append({
            "Domain": d.name,
            "Type": "Domain",
            "Health Score": d.health_score,
            "Status": d.status,
            "Mailforge Status": d.mailforge_status,
            "Campaign Ready": "Yes" if d.campaign_ready else "No",
            "Last Checked": d.last_checked.strftime('%Y-%m-%d %H:%M') if d.last_checked else "Never"
        })
    mailboxes = db.query(Mailbox).all()
    for m in mailboxes:
        data.append({
            "Domain": m.domain.name if m.domain else "Unknown",
            "Type": f"Mailbox ({m.email})",
            "Health Score": m.health_score,
            "Status": m.status,
            "Mailforge Status": m.mailforge_status,
            "Campaign Ready": "Yes" if m.campaign_ready else "No",
            "Last Checked": m.last_checked.strftime('%Y-%m-%d %H:%M') if m.last_checked else "Never"
        })
    df = pd.DataFrame(data)
    stream = io.StringIO()
    df.to_csv(stream, index=False)
    response = Response(content=stream.getvalue(), media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename=mailforge_health_report_{datetime.now().strftime('%Y-%m-%d')}.csv"
    return response

@router.get("/export/issues")
def export_issues(db: Session = Depends(get_db)):
    import pandas as pd
    import io
    
    issues = db.query(Issue).all()
    open_issues = []
    full_history = []
    
    for issue in issues:
        domain_name = issue.domain.name if issue.domain else ""
        mailbox_name = issue.mailbox.email if issue.mailbox else ""
        asset = domain_name or mailbox_name
        
        row = {
            "Severity": issue.severity,
            "Asset": asset,
            "Type": issue.issue_type,
            "Description": issue.description,
            "Recommendation": issue.recommendation,
            "Status": issue.status,
            "Detected Date": issue.detected_at.strftime("%Y-%m-%d %H:%M:%S") if issue.detected_at else "",
            "Resolved Date": issue.resolved_at.strftime("%Y-%m-%d %H:%M:%S") if issue.resolved_at else ""
        }
        full_history.append(row)
        if issue.status == "OPEN":
            open_issues.append(row)
            
    df_open = pd.DataFrame(open_issues) if open_issues else pd.DataFrame(columns=["Severity", "Asset", "Type", "Description", "Recommendation", "Status", "Detected Date", "Resolved Date"])
    df_history = pd.DataFrame(full_history) if full_history else pd.DataFrame(columns=["Severity", "Asset", "Type", "Description", "Recommendation", "Status", "Detected Date", "Resolved Date"])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_open.to_excel(writer, sheet_name="Open", index=False)
        df_history.to_excel(writer, sheet_name="Full History", index=False)
        
    output.seek(0)
    headers = {
        'Content-Disposition': 'attachment; filename="mailforge_health_issues.xlsx"'
    }
    return StreamingResponse(output, headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@router.get("/export/json")
def export_json(db: Session = Depends(get_db)):
    domains = db.query(Domain).all()
    mailboxes = db.query(Mailbox).all()
    issues = db.query(Issue).filter(Issue.status == "OPEN").all()
    
    report_data = {
        "report_date": datetime.now().isoformat(),
        "domains": [{
            "name": d.name,
            "score": d.health_score,
            "status": d.status,
            "campaign_ready": d.campaign_ready,
            "last_checked": d.last_checked.isoformat() if d.last_checked else None
        } for d in domains],
        "mailboxes": [{
            "email": m.email,
            "score": m.health_score,
            "status": m.status,
            "campaign_ready": m.campaign_ready,
            "last_checked": m.last_checked.isoformat() if m.last_checked else None
        } for m in mailboxes],
        "open_issues": [{
            "asset": i.domain.name if i.domain else (i.mailbox.email if i.mailbox else "Global"),
            "severity": i.severity,
            "type": i.issue_type,
            "description": i.description,
            "recommendation": i.recommendation
        } for i in issues]
    }
    
    stream = io.StringIO()
    json.dump(report_data, stream, indent=2)
    response = Response(content=stream.getvalue(), media_type="application/json")
    response.headers["Content-Disposition"] = f"attachment; filename=mailforge_health_report_{datetime.now().strftime('%Y-%m-%d')}.json"
    return response

@router.get("/export/excel")
def export_excel(db: Session = Depends(get_db)):
    import pandas as pd
    domains = db.query(Domain).all()
    dom_data = [{
        "Domain": d.name,
        "Health Score": d.health_score,
        "Status": d.status,
        "Mailforge Status": d.mailforge_status,
        "Campaign Ready": "Yes" if d.campaign_ready else "No",
        "Last Checked": d.last_checked.strftime('%Y-%m-%d %H:%M') if d.last_checked else "Never"
    } for d in domains]
    
    mailboxes = db.query(Mailbox).all()
    mb_data = [{
        "Email": m.email,
        "Health Score": m.health_score,
        "Status": m.status,
        "Mailforge Status": m.mailforge_status,
        "Campaign Ready": "Yes" if m.campaign_ready else "No",
        "Last Checked": m.last_checked.strftime('%Y-%m-%d %H:%M') if m.last_checked else "Never"
    } for m in mailboxes]
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(dom_data).to_excel(writer, sheet_name="Domains", index=False)
        pd.DataFrame(mb_data).to_excel(writer, sheet_name="Mailboxes", index=False)
        
    output.seek(0)
    response = StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response.headers["Content-Disposition"] = f"attachment; filename=mailforge_health_report_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    return response

@router.get("/export/pdf")
def export_pdf(db: Session = Depends(get_db)):
    domains = db.query(Domain).all()
    mailboxes = db.query(Mailbox).all()
    issues = db.query(Issue).filter(Issue.status == "OPEN").all()
    
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1e1b4b'),
        spaceAfter=15
    )
    section_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#312e81'),
        spaceBefore=15,
        spaceAfter=8
    )
    normal_style = styles['Normal']
    
    # Title
    story.append(Paragraph("Mailforge Infrastructure Health Report", title_style))
    story.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}", normal_style))
    story.append(Spacer(1, 15))
    
    # Executive Summary Table
    story.append(Paragraph("Executive Summary", section_style))
    cr_count = sum(1 for m in mailboxes if m.campaign_ready)
    summary_data = [
        ["Total Domains", str(len(domains)), "Total Mailboxes", str(len(mailboxes))],
        ["Healthy Domains", str(sum(1 for d in domains if d.status == 'HEALTHY')), "Campaign Ready Mailboxes", str(cr_count)],
        ["Open Issues", str(len(issues)), "", ""]
    ]
    summary_table = Table(summary_data, colWidths=[120, 120, 150, 120])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('GRID', (0,0), (-1,-1), 1, colors.HexColor('#cbd5e1')),
        ('PADDING', (0,0), (-1,-1), 8),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 15))
    
    # Domain Health Table
    story.append(Paragraph("Domain Health Details", section_style))
    dom_headers = ["Domain", "Score", "Status", "Campaign Ready"]
    dom_rows = [dom_headers]
    for d in domains[:15]:  # Limit top 15 for page fit
        dom_rows.append([d.name, f"{d.health_score}%", d.status, "Yes" if d.campaign_ready else "No"])
    
    dom_table = Table(dom_rows, colWidths=[200, 80, 100, 120])
    dom_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e2e8f0')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('PADDING', (0,0), (-1,-1), 6),
        ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
    ]))
    story.append(dom_table)
    
    doc.build(story)
    pdf_buffer.seek(0)
    
    response = StreamingResponse(pdf_buffer, media_type="application/pdf")
    response.headers["Content-Disposition"] = f"attachment; filename=mailforge_health_report_{datetime.now().strftime('%Y-%m-%d')}.pdf"
    return response
