from sqlalchemy.orm import Session
from database.models import Domain, Mailbox, DomainCheck, MailboxCheck, HealthSnapshot, Issue
from services.mailforge import MailforgeClient
from services.dns_checks import LocalDNSChecker
from services.health_score import calculate_domain_score, calculate_mailbox_score, get_health_category
from datetime import datetime
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

from services.settings_service import get_setting

# Thread pool for running blocking DNS checks concurrently
_scan_pool = ThreadPoolExecutor(max_workers=4)

class HealthScanner:
    def __init__(self, db: Session, settings):
        self.db = db
        self.mailforge = MailforgeClient(get_setting(db, "mailforge_api_key", settings.MAILFORGE_API_KEY))
        self.dns_checker = LocalDNSChecker()
        self.ai = None  # Lazy-load only when needed
        self._settings = settings
        
    def _get_ai(self):
        if self.ai is None:
            from services.openrouter import OpenRouterAI
            self.ai = OpenRouterAI(
                get_setting(self.db, "openrouter_api_key", self._settings.OPENROUTER_API_KEY),
                get_setting(self.db, "openrouter_model", self._settings.OPENROUTER_MODEL or 'meta-llama/llama-3.1-8b-instruct:free')
            )
        return self.ai
        
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

    def _check_single_domain(self, domain_name: str):
        """Run all DNS checks for a single domain (blocking, runs in thread pool)."""
        dns_results = self.dns_checker.run_all(domain_name)
        blacklist_status = self.dns_checker.check_blacklists(domain_name)
        smtp_results = self.dns_checker.check_smtp(domain_name)
        dnssec_status = self.dns_checker.check_dnssec(domain_name)
        mta_sts_status = self.dns_checker.check_mta_sts(domain_name)
        tls_rpt_status = self.dns_checker.check_tls_rpt(domain_name)
        bimi_status = self.dns_checker.check_bimi(domain_name)
        
        return {
            "dns": dns_results,
            "blacklist": blacklist_status,
            "smtp": smtp_results,
            "dnssec": dnssec_status,
            "mta_sts": mta_sts_status,
            "tls_rpt": tls_rpt_status,
            "bimi": bimi_status,
        }

    async def check_all_domains(self):
        domains = self.db.query(Domain).all()
        logger.info(f"Running DNS checks on {len(domains)} domains...")
        
        loop = asyncio.get_event_loop()
        
        # Run all domain checks concurrently in thread pool
        domain_futures = {}
        for domain in domains:
            future = loop.run_in_executor(_scan_pool, self._check_single_domain, domain.name)
            domain_futures[domain.id] = (domain, future)
        
        # Gather all results
        for domain_id, (domain, future) in domain_futures.items():
            try:
                result = await future
                dns_results = result["dns"]
                blacklist_status = result["blacklist"]
                smtp_results = result["smtp"]
                dnssec_status = result["dnssec"]
                mta_sts_status = result["mta_sts"]
                tls_rpt_status = result["tls_rpt"]
                bimi_status = result["bimi"]
                
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
                
                # Create/resolve issues
                self._handle_issues(domain, check, smtp_results, dnssec_status, 
                                     mta_sts_status, tls_rpt_status, bimi_status, mx_health)
                
            except Exception as e:
                logger.error(f"Error checking domain {domain.name}: {e}")
                domain.status = "UNKNOWN"
                domain.last_checked = datetime.utcnow()
                
        self.db.commit()
        logger.info("Domain checks complete")

    def _handle_issues(self, domain, check, smtp_results, dnssec_status, 
                       mta_sts_status, tls_rpt_status, bimi_status, mx_health):
        """Create or resolve issues based on check results."""
        issue_map = [
            (check.spf_status, "SPF", "HIGH", f"SPF record missing or invalid for {domain.name}", "Publish a valid SPF record",
             "MEDIUM", f"SPF record uses a soft policy (~all) for {domain.name}", "Consider changing the policy to strict (-all)"),
            (check.dmarc_status, "DMARC", "HIGH", f"DMARC record missing or invalid for {domain.name}", "Publish a valid DMARC record",
             "MEDIUM", f"DMARC policy is set to p=none for {domain.name}", "Upgrade DMARC policy to p=quarantine or p=reject"),
            (check.dkim_status, "DKIM", "HIGH", f"DKIM records not found for {domain.name}", "Configure DKIM signing and publish the public key",
             None, None, None),
            (mx_health, "MX", "CRITICAL", f"No MX records found for {domain.name}", "Configure MX records",
             None, None, None),
            (check.blacklist_status, "BLACKLIST", "CRITICAL", f"Domain or IP is blacklisted for {domain.name}", "Submit a delisting request",
             None, None, None),
            (dnssec_status, "DNSSEC", "LOW", f"DNSSEC not enabled for {domain.name}", "Enable DNSSEC on your domain registrar",
             None, None, None),
            (mta_sts_status, "MTA-STS", "LOW", f"MTA-STS is not configured for {domain.name}", "Configure MTA-STS for encrypted SMTP",
             None, None, None),
            (tls_rpt_status, "TLS-RPT", "LOW", f"TLS-RPT is not configured for {domain.name}", "Publish a _smtp._tls TXT record",
             None, None, None),
            (bimi_status, "BIMI", "LOW", f"BIMI is not configured for {domain.name}", "Publish a BIMI DNS record",
             None, None, None),
            (check.smtp_status, "SMTP", "HIGH", f"SMTP server unreachable on port 25 for {domain.name}", "Verify mail server is running",
             None, None, None),
            (smtp_results["tls_status"], "SMTP TLS", "MEDIUM", f"SMTP does not support STARTTLS for {domain.name}", "Enable STARTTLS on your SMTP server",
             None, None, None),
        ]
        
        for item in issue_map:
            status, itype, fail_sev, fail_desc, fail_rec, warn_sev, warn_desc, warn_rec = item
            if status == "FAIL":
                self._create_issue(domain.id, None, fail_sev, itype, fail_desc, fail_rec)
            elif status == "WARN" and warn_sev:
                self._create_issue(domain.id, None, warn_sev, itype, warn_desc, warn_rec)
            else:
                self._resolve_issue(domain.id, None, itype)

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
        logger.info("Snapshot generated")

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
