from sqlalchemy.orm import Session
from database.models import Domain, Mailbox, DomainCheck, MailboxCheck, HealthSnapshot, Issue
from services.mailforge import MailforgeClient
from services.dns_checks import LocalDNSChecker
from services.openrouter import OpenRouterAI
from services.health_score import calculate_domain_score, calculate_mailbox_score, get_health_category
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

from services.settings_service import get_setting

class HealthScanner:
    def __init__(self, db: Session, settings):
        self.db = db
        self.mailforge = MailforgeClient(get_setting(db, "mailforge_api_key", settings.MAILFORGE_API_KEY))
        self.dns_checker = LocalDNSChecker()
        self.ai = OpenRouterAI(
            get_setting(db, "openrouter_api_key", settings.OPENROUTER_API_KEY),
            get_setting(db, "openrouter_model", settings.OPENROUTER_MODEL or 'meta-llama/llama-3.1-8b-instruct:free')
        )
        
    async def sync_domains(self):
        logger.info("Syncing domains from Mailforge...")
        domains_data = await self.mailforge.get_domains()
        logger.info(f"Got {len(domains_data)} domains from Mailforge")
        
        for d_data in domains_data:
            domain_name = (
                d_data.get("name") or 
                d_data.get("domain") or 
                d_data.get("domain_name") or
                d_data.get("hostname") or
                ""
            )
            if not domain_name:
                continue
            
            domain_id = str(d_data.get("id") or d_data.get("_id") or d_data.get("domain_id") or "")
            domain_status = str(d_data.get("status") or d_data.get("state") or "UNKNOWN")
            
            domain = self.db.query(Domain).filter(Domain.name == domain_name).first()
            if not domain:
                domain = Domain(
                    name=domain_name,
                    mailforge_id=domain_id,
                    mailforge_status=domain_status
                )
                self.db.add(domain)
            else:
                domain.mailforge_id = domain_id
                domain.mailforge_status = domain_status
                
        self.db.commit()
        logger.info("Domain sync complete")

    async def sync_mailboxes(self):
        logger.info("Syncing mailboxes from Mailforge...")
        mailboxes_data = await self.mailforge.get_mailboxes()
        logger.info(f"Got {len(mailboxes_data)} mailboxes from Mailforge")
        
        for m_data in mailboxes_data:
            email = (
                m_data.get("email") or
                m_data.get("emailAddress") or 
                m_data.get("email_address") or
                m_data.get("address") or
                m_data.get("username") or
                ""
            )
            if not email:
                continue
            
            if "@" not in email:
                domain_part = m_data.get("domain") or m_data.get("domain_name") or ""
                if domain_part:
                    email = f"{email}@{domain_part}"
                else:
                    continue
            
            domain_name = email.split("@")[-1]
            domain = self.db.query(Domain).filter(Domain.name == domain_name).first()
            if not domain:
                domain = Domain(name=domain_name, mailforge_status="UNKNOWN")
                self.db.add(domain)
                self.db.flush()
            
            mailbox_id = str(m_data.get("id") or m_data.get("_id") or m_data.get("mailbox_id") or "")
            mailbox_status = str(m_data.get("status") or m_data.get("state") or "UNKNOWN")
            
            mailbox = self.db.query(Mailbox).filter(Mailbox.email == email).first()
            if not mailbox:
                mailbox = Mailbox(
                    email=email,
                    domain_id=domain.id,
                    mailforge_id=mailbox_id,
                    mailforge_status=mailbox_status,
                    forwarding_status=m_data.get("forwarding") or m_data.get("forwardingStatus") or None
                )
                self.db.add(mailbox)
            else:
                mailbox.mailforge_id = mailbox_id
                mailbox.mailforge_status = mailbox_status
                
        self.db.commit()
        logger.info("Mailbox sync complete")

    async def check_all_domains(self):
        domains = self.db.query(Domain).all()
        logger.info(f"Running DNS checks on {len(domains)} domains...")
        
        for domain in domains:
            try:
                dns_results = self.dns_checker.run_all(domain.name)
                
                blacklist_status = self.dns_checker.check_blacklists(domain.name)
                smtp_results = self.dns_checker.check_smtp(domain.name)
                dnssec_status = self.dns_checker.check_dnssec(domain.name)
                mta_sts_status = self.dns_checker.check_mta_sts(domain.name)
                tls_rpt_status = self.dns_checker.check_tls_rpt(domain.name)
                bimi_status = self.dns_checker.check_bimi(domain.name)
                
                mx_health = "PASS" if dns_results["mx"] else "FAIL"
                
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
                    dnssec_status=dnssec_status,
                    mta_sts_status=mta_sts_status,
                    tls_rpt_status=tls_rpt_status,
                    bimi_status=bimi_status,
                    blacklist_status=blacklist_status,
                    smtp_status=smtp_results["smtp_status"],
                    mx_health=mx_health
                )
                self.db.add(check)
                
                checks_dict = {
                    "mx_status": mx_health,
                    "spf_status": check.spf_status,
                    "dkim_status": check.dkim_status,
                    "dmarc_status": check.dmarc_status,
                    "blacklist_status": check.blacklist_status,
                    "dnssec_status": dnssec_status,
                    "mta_sts_status": check.mta_sts_status,
                    "tls_status": smtp_results["tls_status"],
                    "bimi_status": check.bimi_status,
                    "smtp_status": check.smtp_status
                }
                
                domain.health_score = calculate_domain_score(checks_dict)
                domain.status = get_health_category(domain.health_score)
                
                is_active = (domain.mailforge_status or "").lower() == "active"
                has_critical = domain.status == "CRITICAL"
                
                if not is_active or has_critical:
                    domain.campaign_ready = False
                elif domain.health_score >= 90:
                    domain.campaign_ready = True
                else:
                    domain.campaign_ready = False
                    
                domain.last_checked = datetime.utcnow()
                
                if check.spf_status == "FAIL":
                    self._create_issue(domain.id, None, "HIGH", "SPF", f"SPF record missing or invalid for {domain.name}", "Publish a valid SPF record")
                elif check.spf_status == "WARN":
                    self._create_issue(domain.id, None, "MEDIUM", "SPF", f"SPF record uses a soft policy (~all) for {domain.name}", "Consider changing the policy to strict (-all)")
                else:
                    self._resolve_issue(domain.id, None, "SPF")
                
                if check.dmarc_status == "FAIL":
                    self._create_issue(domain.id, None, "HIGH", "DMARC", f"DMARC record missing or invalid for {domain.name}", "Publish a valid DMARC record")
                elif check.dmarc_status == "WARN":
                    self._create_issue(domain.id, None, "MEDIUM", "DMARC", f"DMARC policy is set to p=none for {domain.name}", "Upgrade DMARC policy to p=quarantine or p=reject to enforce email authentication")
                else:
                    self._resolve_issue(domain.id, None, "DMARC")
                
                if mx_health == "FAIL":
                    self._create_issue(domain.id, None, "CRITICAL", "MX", f"No MX records found for {domain.name}", "Configure MX records to handle incoming emails")
                else:
                    self._resolve_issue(domain.id, None, "MX")
                
                if check.dkim_status == "FAIL":
                    self._create_issue(domain.id, None, "HIGH", "DKIM", f"DKIM records not found or invalid for {domain.name}", "Configure DKIM signing in your mail server and publish the public key record")
                else:
                    self._resolve_issue(domain.id, None, "DKIM")
                
                if check.blacklist_status == "FAIL":
                    self._create_issue(domain.id, None, "CRITICAL", "BLACKLIST", f"Domain or IP is blacklisted for {domain.name}", "Check blacklist details and submit a delisting request")
                else:
                    self._resolve_issue(domain.id, None, "BLACKLIST")
                    
                if dnssec_status == "FAIL":
                    self._create_issue(domain.id, None, "LOW", "DNSSEC", f"DNSSEC not enabled for {domain.name}", "Enable DNSSEC on your domain registrar to prevent DNS spoofing")
                else:
                    self._resolve_issue(domain.id, None, "DNSSEC")
                    
                if mta_sts_status == "FAIL":
                    self._create_issue(domain.id, None, "LOW", "MTA-STS", f"MTA-STS is not configured for {domain.name}", "Configure MTA-STS to enforce encrypted SMTP connections")
                else:
                    self._resolve_issue(domain.id, None, "MTA-STS")
                    
                if tls_rpt_status == "FAIL":
                    self._create_issue(domain.id, None, "LOW", "TLS-RPT", f"SMTP TLS Reporting (TLS-RPT) is not configured for {domain.name}", "Publish a _smtp._tls TXT record to receive TLS connectivity reports")
                else:
                    self._resolve_issue(domain.id, None, "TLS-RPT")
                    
                if bimi_status == "FAIL":
                    self._create_issue(domain.id, None, "LOW", "BIMI", f"BIMI is not configured for {domain.name}", "Publish a BIMI DNS record to show your brand logo in supporting inbox clients")
                else:
                    self._resolve_issue(domain.id, None, "BIMI")
                    
                if smtp_results["smtp_status"] == "FAIL":
                    self._create_issue(domain.id, None, "HIGH", "SMTP", f"SMTP server is offline or unreachable on port 25 for {domain.name}", "Verify your mail server is running and port 25 is open")
                else:
                    self._resolve_issue(domain.id, None, "SMTP")
                    
                if smtp_results["tls_status"] == "FAIL":
                    self._create_issue(domain.id, None, "MEDIUM", "SMTP TLS", f"SMTP server does not support STARTTLS for {domain.name}", "Enable TLS/STARTTLS on your SMTP server to encrypt messages in transit")
                else:
                    self._resolve_issue(domain.id, None, "SMTP TLS")
                
            except Exception as e:
                logger.error(f"Error checking domain {domain.name}: {e}")
                domain.status = "UNKNOWN"
                domain.last_checked = datetime.utcnow()
                
        self.db.commit()
        logger.info("Domain checks complete")

    async def check_all_mailboxes(self):
        mailboxes = self.db.query(Mailbox).all()
        logger.info(f"Running checks on {len(mailboxes)} mailboxes...")
        
        for mb in mailboxes:
            try:
                domain = self.db.query(Domain).filter(Domain.id == mb.domain_id).first()
                d_score = domain.health_score if domain else 0.0
                
                domain_checks = {}
                if domain and domain.checks:
                    latest_dc = domain.checks[-1]
                    domain_checks = {
                        "mx_status": latest_dc.mx_health,
                        "spf_status": latest_dc.spf_status,
                        "dkim_status": latest_dc.dkim_status,
                        "dmarc_status": latest_dc.dmarc_status,
                        "smtp_connectivity": latest_dc.smtp_status,
                        "mailbox_verification": "PASS"
                    }
                
                check = MailboxCheck(
                    mailbox_id=mb.id,
                    smtp_connectivity=domain_checks.get("smtp_connectivity", "UNKNOWN"),
                    mailbox_verification=domain_checks.get("mailbox_verification", "UNKNOWN")
                )
                self.db.add(check)
                
                mb.health_score = calculate_mailbox_score(d_score, domain_checks, mb.mailforge_status or "")
                mb.status = get_health_category(mb.health_score)
                
                is_active = (mb.mailforge_status or "").lower() == "active"
                has_critical = mb.status == "CRITICAL"
                
                if not is_active or has_critical:
                    mb.campaign_ready = False
                elif mb.health_score >= 90:
                    mb.campaign_ready = True
                else:
                    mb.campaign_ready = False
                    
                mb.last_checked = datetime.utcnow()
            except Exception as e:
                logger.error(f"Error checking mailbox {mb.email}: {e}")
                mb.status = "UNKNOWN"
                mb.last_checked = datetime.utcnow()
            
        self.db.commit()
        logger.info("Mailbox checks complete")

    def _create_issue(self, domain_id, mailbox_id, severity, issue_type, desc, recommendation):
        existing = self.db.query(Issue).filter(
            Issue.domain_id == domain_id,
            Issue.mailbox_id == mailbox_id,
            Issue.issue_type == issue_type,
            Issue.status == "OPEN"
        ).first()
        
        if existing:
            existing.last_seen_at = datetime.utcnow()
        else:
            issue = Issue(
                domain_id=domain_id,
                mailbox_id=mailbox_id,
                severity=severity,
                issue_type=issue_type,
                description=desc,
                recommendation=recommendation,
                status="OPEN"
            )
            self.db.add(issue)

    def _resolve_issue(self, domain_id, mailbox_id, issue_type):
        existing = self.db.query(Issue).filter(
            Issue.domain_id == domain_id,
            Issue.mailbox_id == mailbox_id,
            Issue.issue_type == issue_type,
            Issue.status == "OPEN"
        ).first()
        if existing:
            existing.status = "RESOLVED"
            logger.info(f"Resolved issue: {issue_type} for domain_id {domain_id}")

    async def generate_snapshot(self):
        domains = self.db.query(Domain).all()
        mailboxes = self.db.query(Mailbox).all()
        
        t_domains = len(domains)
        h_domains = sum(1 for d in domains if d.status == "HEALTHY")
        
        t_mailboxes = len(mailboxes)
        h_mailboxes = sum(1 for m in mailboxes if m.status == "HEALTHY")
        cr_mailboxes = sum(1 for m in mailboxes if m.campaign_ready)
        
        overall = 0.0
        if t_domains > 0:
            overall = sum(d.health_score for d in domains) / t_domains
            
        snap = HealthSnapshot(
            overall_score=overall,
            healthy_domains=h_domains,
            total_domains=t_domains,
            healthy_mailboxes=h_mailboxes,
            total_mailboxes=t_mailboxes,
            campaign_ready_mailboxes=cr_mailboxes
        )
        self.db.add(snap)
        self.db.commit()
        logger.info(f"Snapshot generated")

    async def run_full_scan(self):
        logger.info("=== FULL SCAN STARTED ===")
        try:
            await self.sync_domains()
            await self.sync_mailboxes()
            await self.check_all_domains()
            await self.check_all_mailboxes()
            await self.generate_snapshot()
            logger.info("=== FULL SCAN COMPLETED ===")
        except Exception as e:
            logger.error(f"=== FULL SCAN FAILED: {e} ===")
            raise
