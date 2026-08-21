import dns.resolver
import dns.exception
import dns.message
import dns.query
import dns.flags
import dns.rdatatype
import smtplib
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class LocalDNSChecker:
    def __init__(self):
        self.resolver = dns.resolver.Resolver()
        self.resolver.timeout = 5
        self.resolver.lifetime = 5
        
    def _safe_resolve(self, domain: str, rdtype: str) -> List[str]:
        try:
            answers = self.resolver.resolve(domain, rdtype)
            return [str(rdata).strip('"') for rdata in answers]
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.exception.Timeout, dns.resolver.NoNameservers, dns.name.EmptyLabel):
            return []
        except Exception as e:
            logger.debug(f"DNS resolution error for {domain} ({rdtype}): {e}")
            return []

    def get_a(self, domain: str) -> List[str]:
        return self._safe_resolve(domain, "A")
        
    def get_aaaa(self, domain: str) -> List[str]:
        return self._safe_resolve(domain, "AAAA")
        
    def get_mx(self, domain: str) -> List[str]:
        return self._safe_resolve(domain, "MX")
        
    def get_txt(self, domain: str) -> List[str]:
        return self._safe_resolve(domain, "TXT")
        
    def get_ns(self, domain: str) -> List[str]:
        return self._safe_resolve(domain, "NS")
        
    def get_cname(self, domain: str) -> List[str]:
        return self._safe_resolve(domain, "CNAME")

    def check_spf(self, domain: str) -> str:
        txt_records = self.get_txt(domain)
        for record in txt_records:
            if record.startswith("v=spf1"):
                if "-all" in record:
                    return "PASS"
                elif "~all" in record or "?all" in record:
                    return "WARN"
                return "PASS"
        return "FAIL"

    def check_dmarc(self, domain: str) -> str:
        dmarc_domain = f"_dmarc.{domain}"
        txt_records = self.get_txt(dmarc_domain)
        for record in txt_records:
            if record.startswith("v=DMARC1"):
                if "p=reject" in record or "p=quarantine" in record:
                    return "PASS"
                if "p=none" in record:
                    return "WARN"
        return "FAIL"

    def check_dkim(self, domain: str) -> str:
        selectors = ["default", "mail", "google", "selector1", "selector2", "s1", "s2", "dkim", "k1", "mxvault"]
        for sel in selectors:
            records = self.get_txt(f"{sel}._domainkey.{domain}")
            for r in records:
                if "v=DKIM1" in r or "p=" in r:
                    return "PASS"
        return "FAIL"

    def check_dnssec(self, domain: str) -> str:
        try:
            req = dns.message.make_query(domain, dns.rdatatype.A, want_dnssec=True)
            nameservers = dns.resolver.Resolver().nameservers
            if not nameservers:
                return "UNKNOWN"
            res = dns.query.udp(req, nameservers[0], timeout=5)
            if res.flags & dns.flags.AD:
                return "PASS"
            return "FAIL"
        except Exception:
            return "UNKNOWN"

    def check_mta_sts(self, domain: str) -> str:
        records = self.get_txt(f"_mta-sts.{domain}")
        for r in records:
            if r.startswith("v=STSv1"):
                return "PASS"
        return "FAIL"

    def check_tls_rpt(self, domain: str) -> str:
        records = self.get_txt(f"_smtp._tls.{domain}")
        for r in records:
            if r.startswith("v=TLSRPTv1"):
                return "PASS"
        return "FAIL"

    def check_bimi(self, domain: str) -> str:
        records = self.get_txt(f"default._bimi.{domain}")
        for r in records:
            if r.startswith("v=BIMI1"):
                return "PASS"
        return "FAIL"

    def check_blacklists(self, domain: str) -> str:
        bls = ["zen.spamhaus.org", "bl.spamcop.net", "b.barracudacentral.org", "dnsbl.sorbs.net", "spam.dnsbl.sorbs.net"]
        ips = self.get_a(domain)
        if not ips:
            return "UNKNOWN"
        ip = ips[0]
        reversed_ip = ".".join(reversed(ip.split(".")))
        for bl in bls:
            try:
                ans = self.resolver.resolve(f"{reversed_ip}.{bl}", "A")
                if ans:
                    return "FAIL"
            except Exception:
                pass
        return "PASS"

    def check_smtp(self, domain: str) -> Dict[str, str]:
        mx_records = self.get_mx(domain)
        if not mx_records:
            return {"smtp_status": "FAIL", "tls_status": "FAIL"}
        
        try:
            mx_list = [(int(r.split()[0]), r.split()[1]) for r in mx_records if len(r.split()) == 2]
            mx_list.sort(key=lambda x: x[0])
            mx_host = mx_list[0][1].strip('.')
        except Exception:
            mx_host = mx_records[0].split()[-1].strip('.')

        smtp_status = "FAIL"
        tls_status = "FAIL"
        try:
            server = smtplib.SMTP(mx_host, 25, timeout=5)
            smtp_status = "PASS"
            server.ehlo_or_helo_if_needed()
            if server.has_extn('STARTTLS'):
                server.starttls()
                tls_status = "PASS"
            server.quit()
        except Exception as e:
            logger.debug(f"SMTP check error for {domain}: {e}")
            
        return {"smtp_status": smtp_status, "tls_status": tls_status}

    def run_all(self, domain: str) -> Dict:
        return {
            "a": self.get_a(domain),
            "aaaa": self.get_aaaa(domain),
            "mx": self.get_mx(domain),
            "txt": self.get_txt(domain),
            "ns": self.get_ns(domain),
            "cname": self.get_cname(domain),
            "spf_status": self.check_spf(domain),
            "dmarc_status": self.check_dmarc(domain),
            "dkim_status": self.check_dkim(domain),
        }
