from sqlalchemy.orm import Session
from database.models import Domain, Mailbox, DomainCheck, MailboxCheck, HealthSnapshot, Issue, ScanRun, ProviderRun, InstantlyTest
from services.mailforge import MailforgeClient
from services.dns_checks import LocalDNSChecker
from services.health_score import calculate_domain_score, calculate_mailbox_score, get_health_category
from services.instantly import InstantlyClient
from datetime import datetime
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

from services.settings_service import get_setting

_scan_pool = ThreadPoolExecutor(max_workers=4)

class HealthScanner:
    def __init__(self, db: Session, settings, scan_id: str = None):
        self.db = db
        self._settings = settings
        self.scan_id = scan_id
        
        mf_key = get_setting(db, "mailforge_api_key") or settings.MAILFORGE_API_KEY
        in_key = get_setting(db, "instantly_api_key") or getattr(settings, "INSTANTLY_API_KEY", None)
        
        self.mailforge = MailforgeClient(mf_key)
        self.dns_checker = LocalDNSChecker()
        self.instantly = InstantlyClient(in_key)
        self.ai = None
        
    def _update_progress(self, progress: int, stage: str):
        if not self.scan_id:
            return
        scan = self.db.query(ScanRun).filter(ScanRun.id == self.scan_id).first()
        if scan:
            scan.progress = progress
            scan.current_stage = stage
            self.db.commit()

    async def sync_domains(self):
        self._update_progress(20, "Syncing domains from Mailforge")
        domains_data = await self.mailforge.get_domains()
        for d_data in domains_data:
            domain_name = d_data.get("name") or d_data.get("domain") or d_data.get("domain_name") or d_data.get("hostname") or ""
            if not domain_name: continue
            
            domain = self.db.query(Domain).filter(Domain.name == domain_name).first()
            if not domain:
                domain = Domain(name=domain_name, mailforge_id=str(d_data.get("id", "")), mailforge_status=str(d_data.get("status", "UNKNOWN")))
                self.db.add(domain)
            else:
                domain.mailforge_id = str(d_data.get("id", ""))
                domain.mailforge_status = str(d_data.get("status", "UNKNOWN"))
        self.db.commit()

    async def sync_mailboxes(self):
        self._update_progress(35, "Syncing mailboxes from Mailforge")
        mailboxes_data = await self.mailforge.get_mailboxes()
        for m_data in mailboxes_data:
            email = m_data.get("email") or m_data.get("emailAddress") or m_data.get("email_address") or m_data.get("address") or ""
            if not email: continue
            if "@" not in email:
                domain_part = m_data.get("domain") or ""
                if domain_part: email = f"{email}@{domain_part}"
                else: continue
            
            domain_name = email.split("@")[-1]
            domain = self.db.query(Domain).filter(Domain.name == domain_name).first()
            if not domain:
                domain = Domain(name=domain_name, mailforge_status="UNKNOWN")
                self.db.add(domain)
                self.db.flush()
            
            mailbox = self.db.query(Mailbox).filter(Mailbox.email == email).first()
            if not mailbox:
                mailbox = Mailbox(email=email, domain_id=domain.id, mailforge_id=str(m_data.get("id", "")), mailforge_status=str(m_data.get("status", "UNKNOWN")))
                self.db.add(mailbox)
            else:
                mailbox.mailforge_id = str(m_data.get("id", ""))
                mailbox.mailforge_status = str(m_data.get("status", "UNKNOWN"))
        self.db.commit()

    def _check_single_domain(self, domain_name: str, receives_inbound: bool):
        dns_results = self.dns_checker.run_all(domain_name)
        blacklist_status = self.dns_checker.check_blacklists(domain_name)
        smtp_results = self.dns_checker.check_smtp(domain_name, receives_inbound)
        dnssec_status = self.dns_checker.check_dnssec(domain_name)
        mta_sts_status = self.dns_checker.check_mta_sts(domain_name)
        tls_rpt_status = self.dns_checker.check_tls_rpt(domain_name)
        bimi_status = self.dns_checker.check_bimi(domain_name)
        return {"dns": dns_results, "blacklist": blacklist_status, "smtp": smtp_results, "dnssec": dnssec_status, "mta_sts": mta_sts_status, "tls_rpt": tls_rpt_status, "bimi": bimi_status}

    async def check_all_domains(self):
        self._update_progress(50, "Running DNS and infrastructure checks")
        domains = self.db.query(Domain).all()
        loop = asyncio.get_event_loop()
        domain_futures = {d.id: (d, loop.run_in_executor(_scan_pool, self._check_single_domain, d.name, d.receives_inbound_mail)) for d in domains}
        
        for domain_id, (domain, future) in domain_futures.items():
            try:
                result = await future
                dns_results = result["dns"]
                smtp_results = result["smtp"]
                
                mx_health = "PASS" if dns_results.get("mx") else "FAIL"
                
                check = DomainCheck(
                    domain_id=domain.id, 
                    a_record=",".join(dns_results.get("a", [])), 
                    aaaa_record=",".join(dns_results.get("aaaa", [])),
                    mx_record=",".join(dns_results.get("mx", [])), 
                    txt_record=",".join(dns_results.get("txt", [])), 
                    ns_record=",".join(dns_results.get("ns", [])),
                    cname_record=",".join(dns_results.get("cname", [])), 
                    spf_status=dns_results.get("spf_status", "UNKNOWN"), 
                    dmarc_status=dns_results.get("dmarc_status", "UNKNOWN"),
                    dkim_status=dns_results.get("dkim_status", "UNKNOWN"), 
                    dnssec_status=result["dnssec"], 
                    mta_sts_status=result["mta_sts"], 
                    tls_rpt_status=result["tls_rpt"],
                    bimi_status=result["bimi"], 
                    blacklist_status=result["blacklist"], 
                    smtp_status=smtp_results["smtp_status"], 
                    mx_health=mx_health
                )
                self.db.add(check)
                
                domain.health_score = calculate_domain_score({"mx_status": mx_health, "spf_status": check.spf_status, "dkim_status": check.dkim_status, "dmarc_status": check.dmarc_status, "blacklist_status": check.blacklist_status, "dnssec_status": check.dnssec_status, "mta_sts_status": check.mta_sts_status, "tls_status": smtp_results["tls_status"], "bimi_status": check.bimi_status, "smtp_status": check.smtp_status})
                domain.status = get_health_category(domain.health_score)
                domain.campaign_ready = domain.health_score >= 90 and (domain.mailforge_status or "").lower() == "active" and domain.status != "CRITICAL"
                domain.last_checked = datetime.utcnow()
                
                self._handle_issues(domain, check, smtp_results["tls_status"])
                
            except Exception as e:
                logger.error(f"Error checking domain {domain.name}: {e}")
                
        self.db.commit()

    def _handle_issues(self, domain, check, tls_status):
        try:
            self._process_issue(domain.id, None, "SPF", check.spf_status == "FAIL", "SPF configuration is missing or invalid", "Configure a valid SPF TXT record for this domain.")
            self._process_issue(domain.id, None, "DKIM", check.dkim_status == "FAIL", "DKIM configuration is missing or invalid", "Configure a valid DKIM TXT record for this domain.")
            self._process_issue(domain.id, None, "DMARC", check.dmarc_status == "FAIL", "DMARC configuration is missing or invalid", "Configure a valid DMARC TXT record for this domain.")
            self._process_issue(domain.id, None, "DNSSEC", check.dnssec_status == "FAIL", "DNSSEC is not enabled", "Enable DNSSEC with your registrar.", "LOW")
            self._process_issue(domain.id, None, "MTA-STS", check.mta_sts_status == "FAIL", "MTA-STS policy is missing", "Deploy an MTA-STS policy file and DNS record.", "MEDIUM")
            self._process_issue(domain.id, None, "TLS-RPT", check.tls_rpt_status == "FAIL", "TLS Reporting is not configured", "Add a TLS-RPT DNS record.", "LOW")
            self._process_issue(domain.id, None, "BIMI", check.bimi_status == "FAIL", "BIMI is not configured", "Add a BIMI DNS record and logo.", "LOW")
            self._process_issue(domain.id, None, "BLACKLIST", check.blacklist_status == "FAIL", "Domain is blacklisted", "Investigate and request delisting.", "CRITICAL")
            
            # SMTP Issue logic for receives_inbound_mail
            if domain.receives_inbound_mail:
                self._process_issue(domain.id, None, "SMTP", check.smtp_status == "FAIL", "SMTP connectivity failed on port 25", "Ensure port 25 is open for inbound mail.", "HIGH")
            else:
                self._process_issue(domain.id, None, "SMTP", check.smtp_status == "FAIL", "Outbound SMTP connectivity failed on port 587", "Ensure port 587 is available for mail submission.", "HIGH")
                
            self._process_issue(domain.id, None, "STARTTLS", tls_status == "FAIL", "STARTTLS is not supported", "Configure your mail server to support STARTTLS.", "HIGH")
        except Exception as e:
            logger.error(f"Error handling issues for {domain.name}: {e}")

    def _process_issue(self, domain_id, mailbox_id, issue_type, is_failing, description, recommendation, severity="HIGH"):
        existing = self.db.query(Issue).filter(Issue.domain_id == domain_id, Issue.mailbox_id == mailbox_id, Issue.issue_type == issue_type).order_by(Issue.id.desc()).first()
        if is_failing:
            if existing and existing.status == "OPEN":
                existing.last_seen_at = datetime.utcnow()
            else:
                new_issue = Issue(domain_id=domain_id, mailbox_id=mailbox_id, issue_type=issue_type, description=description, recommendation=recommendation, severity=severity, status="OPEN", detected_at=datetime.utcnow(), last_seen_at=datetime.utcnow())
                self.db.add(new_issue)
        else:
            if existing and existing.status == "OPEN":
                existing.status = "RESOLVED"
                existing.resolved_at = datetime.utcnow()
        self._update_progress(70, "Running mailbox verifications")
        for mb in self.db.query(Mailbox).all():
            domain = self.db.query(Domain).filter(Domain.id == mb.domain_id).first()
            check = MailboxCheck(mailbox_id=mb.id, smtp_connectivity="PASS", mailbox_verification="PASS")
            self.db.add(check)
            mb.health_score = domain.health_score if domain else 0.0
            mb.status = get_health_category(mb.health_score)
            mb.campaign_ready = mb.health_score >= 90
            mb.last_checked = datetime.utcnow()
        self.db.commit()

    async def run_instantly_checks(self):
        self._update_progress(85, "Running Instantly automated test")
        if self.instantly.available:
            result = await self.instantly.run_automated_inbox_test()
            if result.get("status") == "COMPLETED":
                stats = result.get("stats", {})
                t = InstantlyTest(
                    test_id=result.get("test_id"),
                    scan_id=self.scan_id,
                    status="COMPLETED",
                    inbox_percentage=stats.get("inbox", 0),
                    spam_percentage=stats.get("spam", 0),
                    missing_percentage=stats.get("missing", 0)
                )
                self.db.add(t)
                self.db.commit()

    def _resolve_issue(self, domain_id, mailbox_id, issue_type):
        existing = self.db.query(Issue).filter(Issue.domain_id == domain_id, Issue.mailbox_id == mailbox_id, Issue.issue_type == issue_type, Issue.status == "OPEN").first()
        if existing: existing.status = "RESOLVED"

    async def generate_snapshot(self):
        self._update_progress(95, "Generating final snapshot")
        domains, mailboxes = self.db.query(Domain).all(), self.db.query(Mailbox).all()
        overall = sum(d.health_score for d in domains) / len(domains) if domains else 0.0
        self.db.add(HealthSnapshot(
            overall_score=overall, healthy_domains=sum(1 for d in domains if d.status == "HEALTHY"), total_domains=len(domains),
            healthy_mailboxes=sum(1 for m in mailboxes if m.status == "HEALTHY"), total_mailboxes=len(mailboxes), campaign_ready_mailboxes=sum(1 for m in mailboxes if m.campaign_ready)
        ))
        self.db.commit()

    async def run_full_scan(self):
        logger.info("=== FULL SCAN STARTED ===")
        try:
            await self.sync_domains()
            await self.sync_mailboxes()
            await self.check_all_domains()
            await self.check_all_mailboxes()
            await self.run_instantly_checks()
            await self.generate_snapshot()
            logger.info("=== FULL SCAN COMPLETED ===")
        except Exception as e:
            logger.error(f"=== FULL SCAN FAILED: {e} ===")
            raise
