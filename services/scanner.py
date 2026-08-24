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
        smtp_results = self.dns_checker.check_smtp(domain_name, receives_inbound)
        dnssec_status = self.dns_checker.check_dnssec(domain_name)
        mta_sts_status = self.dns_checker.check_mta_sts(domain_name)
        tls_rpt_status = self.dns_checker.check_tls_rpt(domain_name)
        bimi_status = self.dns_checker.check_bimi(domain_name)
        
        resolved_ips = self.dns_checker.resolve_domain_ips(domain_name)
        
        from config.blacklist_providers import BLACKLIST_PROVIDERS
        provider_results = []
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=15) as bl_executor:
            futures = []
            
            # DNSBLs for IPs
            for ip in resolved_ips:
                for p in BLACKLIST_PROVIDERS:
                    if p["enabled"] and p["type"] == "IP":
                        futures.append(bl_executor.submit(
                            lambda ip_arg=ip, p_arg=p: {**self.dns_checker.check_ip_dnsbl(ip_arg, p_arg["zone"], p_arg.get("timeout_ms", 3000)), "provider": p_arg["name"], "category": "IP_BLACKLIST", "ip": ip_arg}
                        ))
                        
            # DBLs for Domain
            for p in BLACKLIST_PROVIDERS:
                if p["enabled"] and p["type"] == "DOMAIN":
                    futures.append(bl_executor.submit(
                        lambda p_arg=p: {**self.dns_checker.check_domain_dbl(domain_name, p_arg["zone"], p_arg.get("timeout_ms", 3000)), "provider": p_arg["name"], "category": "DOMAIN_BLACKLIST", "ip": None}
                    ))
                    
            for f in as_completed(futures):
                try:
                    provider_results.append(f.result())
                except Exception:
                    pass
                    
        return {
            "dns": dns_results, 
            "smtp": smtp_results, 
            "dnssec": dnssec_status, 
            "mta_sts": mta_sts_status, 
            "tls_rpt": tls_rpt_status, 
            "bimi": bimi_status,
            "resolved_ips": resolved_ips,
            "provider_results": provider_results
        }

    async def check_all_domains(self):
        from services.reputation_engine import calculate_reputation_status
        from services.abuseipdb import AbuseIPDBClient
        from config.settings import settings
        
        self._update_progress(50, "Running DNS and infrastructure checks")
        domains = self.db.query(Domain).all()
        loop = asyncio.get_event_loop()
        
        # Shared cache for the scan run to prevent duplicate checks
        _abuseipdb_cache = {}
        
        domain_futures = {d.id: (d, loop.run_in_executor(_scan_pool, self._check_single_domain, d.name, d.receives_inbound_mail)) for d in domains}
        
        abuse_client = AbuseIPDBClient(api_key=settings.ABUSEIPDB_API_KEY)
        
        for domain_id, (domain, future) in domain_futures.items():
            try:
                result = await future
                dns_results = result["dns"]
                smtp_results = result["smtp"]
                resolved_ips = result["resolved_ips"]
                provider_results = result["provider_results"]
                
                # Check AbuseIPDB for each IP asynchronously with caching
                ip_reputation_data = []
                for ip in resolved_ips:
                    if ip not in _abuseipdb_cache:
                        _abuseipdb_cache[ip] = await abuse_client.check_ip(ip)
                    ip_reputation_data.append(_abuseipdb_cache[ip])
                    
                # Calculate final reputation status
                reputation = calculate_reputation_status(provider_results)
                final_blacklist_status = reputation["status"]
                
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
                    blacklist_status=final_blacklist_status,
                    blacklist_details=reputation,
                    ip_reputation=ip_reputation_data,
                    resolved_ips=resolved_ips,
                    smtp_status=smtp_results["smtp_status"], 
                    mx_health=mx_health
                )
                self.db.add(check)
                
                domain.health_score = calculate_domain_score({"mx_status": mx_health, "spf_status": check.spf_status, "dkim_status": check.dkim_status, "dmarc_status": check.dmarc_status, "blacklist_status": final_blacklist_status, "dnssec_status": check.dnssec_status, "mta_sts_status": check.mta_sts_status, "tls_status": smtp_results["tls_status"], "bimi_status": check.bimi_status, "smtp_status": check.smtp_status})
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
            # Advanced DNS checks (DNSSEC, MTA-STS, TLS-RPT, BIMI) are intentionally skipped 
            # for the issue tracker because these are cold-emailing domains and those 
            # records are overkill / not strictly necessary.
            self._process_issue(domain.id, None, "BLACKLIST", check.blacklist_status == "BLACKLISTED", "Domain or IP is blacklisted", "Investigate provider listings and request delisting.", "CRITICAL")
            
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
            open_issues = self.db.query(Issue).filter(Issue.domain_id == domain_id, Issue.mailbox_id == mailbox_id, Issue.issue_type == issue_type, Issue.status == "OPEN").all()
            for issue in open_issues:
                issue.status = "RESOLVED"
                issue.resolved_at = datetime.utcnow()

    async def check_all_mailboxes(self):
        self._update_progress(70, "Running authenticated mailbox verifications")
        mailboxes = self.db.query(Mailbox).all()
        
        loop = asyncio.get_event_loop()
        mb_futures = {mb.id: (mb, loop.run_in_executor(_scan_pool, self._check_single_mailbox, mb)) for mb in mailboxes}
        
        for mb_id, (mb, future) in mb_futures.items():
            try:
                domain = self.db.query(Domain).filter(Domain.id == mb.domain_id).first()
                result = await future
                smtp_status = result["smtp_status"]
                imap_status = result["imap_status"]
                auth_status = result["auth_status"]
                
                check = MailboxCheck(
                    mailbox_id=mb.id, 
                    smtp_connectivity=smtp_status, 
                    imap_connectivity=imap_status,
                    auth_status=auth_status,
                    mailbox_verification="PASS" if auth_status == "PASS" else "FAIL"
                )
                self.db.add(check)
                
                domain_score = domain.health_score if domain else 0.0
                mb.health_score = domain_score if auth_status == "PASS" else 0.0
                mb.status = get_health_category(mb.health_score)
                mb.campaign_ready = mb.health_score >= 90 and auth_status == "PASS"
                mb.last_checked = datetime.utcnow()
                
                self._process_issue(domain.id if domain else None, mb.id, "SMTP_AUTH", smtp_status == "FAIL", "Mailbox cannot authenticate via SMTP", "Verify SMTP credentials and server settings.", "CRITICAL")
                self._process_issue(domain.id if domain else None, mb.id, "IMAP_AUTH", imap_status == "FAIL", "Mailbox cannot authenticate via IMAP", "Verify IMAP credentials and server settings.", "CRITICAL")
            except Exception as e:
                logger.error(f"Error checking mailbox {mb.email}: {e}")
                
        self.db.commit()

    def _check_single_mailbox(self, mb):
        import smtplib
        import imaplib
        smtp_status = "UNKNOWN"
        imap_status = "UNKNOWN"
        auth_status = "UNKNOWN"
        
        if mb.password and mb.smtp_host and mb.imap_host:
            try:
                server = smtplib.SMTP(mb.smtp_host, mb.smtp_port or 587, timeout=5)
                server.starttls()
                server.login(mb.email, mb.password)
                server.quit()
                smtp_status = "PASS"
                auth_status = "PASS"
            except Exception as e:
                logger.error(f"SMTP Auth failed for {mb.email}: {e}")
                smtp_status = "FAIL"
                auth_status = "FAIL"
            
            try:
                imap = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port or 993, timeout=5)
                imap.login(mb.email, mb.password)
                imap.logout()
                imap_status = "PASS"
            except Exception as e:
                logger.error(f"IMAP Auth failed for {mb.email}: {e}")
                imap_status = "FAIL"
                auth_status = "FAIL"
        else:
            smtp_status = "PASS"
            imap_status = "PASS"
            auth_status = "PASS"
            
        return {"smtp_status": smtp_status, "imap_status": imap_status, "auth_status": auth_status}

    async def run_instantly_checks(self):
        self._update_progress(85, "Running Instantly automated test")
        if self.instantly.available:
            result = await self.instantly.run_automated_inbox_test()
            stats = result.get("stats", {})
            t = InstantlyTest(
                test_id=result.get("test_id", "none"),
                scan_id=self.scan_id,
                status=result.get("status", "FAILED"),
                inbox_percentage=stats.get("inbox", 0),
                spam_percentage=stats.get("spam", 0),
                missing_percentage=stats.get("missing", 0),
                raw_results=result.get("error", None)
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
