import dns.resolver
import dns.exception
import dns.message
import dns.query
import dns.flags
import dns.rdatatype
import socket
import logging
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# Shared thread pool for parallel DNS / network lookups
_executor = ThreadPoolExecutor(max_workers=8)

class LocalDNSChecker:
    def __init__(self):
        self.resolver = dns.resolver.Resolver()
        self.resolver.timeout = 3
        self.resolver.lifetime = 3
        
    def _safe_resolve(self, domain: str, rdtype: str) -> List[str]:
        try:
            answers = self.resolver.resolve(domain, rdtype)
            return [str(rdata).strip('"') for rdata in answers]
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.exception.Timeout,
                dns.resolver.NoNameservers, dns.name.EmptyLabel):
            return []
        except Exception:
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

    def check_spf(self, txt_records: List[str]) -> str:
        """Check SPF from pre-fetched TXT records (avoids duplicate query)."""
        for record in txt_records:
            if record.startswith("v=spf1"):
                if "-all" in record:
                    return "PASS"
                elif "~all" in record or "?all" in record:
                    return "WARN"
                return "PASS"
        return "FAIL"

    def check_dmarc(self, domain: str) -> str:
        records = self._safe_resolve(f"_dmarc.{domain}", "TXT")
        for record in records:
            if record.startswith("v=DMARC1"):
                if "p=reject" in record or "p=quarantine" in record:
                    return "PASS"
                if "p=none" in record:
                    return "WARN"
        return "FAIL"

    def _check_dkim_selector(self, domain: str, sel: str) -> bool:
        """Check a single DKIM selector. Returns True if found."""
        records = self._safe_resolve(f"{sel}._domainkey.{domain}", "TXT")
        for r in records:
            if "v=DKIM1" in r or "p=" in r:
                return True
        return False

    def check_dkim(self, domain: str) -> str:
        """Check DKIM in parallel across common selectors."""
        selectors = ["default", "google", "selector1", "selector2", "s1", "dkim", "mail", "k1"]
        futures = {_executor.submit(self._check_dkim_selector, domain, sel): sel for sel in selectors}
        for future in as_completed(futures, timeout=6):
            try:
                if future.result():
                    # Cancel remaining futures
                    for f in futures:
                        f.cancel()
                    return "PASS"
            except Exception:
                pass
        return "FAIL"

    def check_blacklists(self, domain: str) -> str:
        # Deprecated: use the new multi-source blacklist check instead
        return "PASS"

    def resolve_domain_ips(self, domain: str) -> List[str]:
        ips = set()
        
        # Get A records
        try:
            a_records = dns.resolver.resolve(domain, 'A', lifetime=3.0)
            for r in a_records: ips.add(r.to_text())
        except Exception: pass
        
        # Get AAAA records
        try:
            aaaa = dns.resolver.resolve(domain, 'AAAA', lifetime=3.0)
            for r in aaaa: ips.add(r.to_text())
        except Exception: pass
        
        # Get MX records and their A records
        mx_records = self.get_mx(domain)
        for mx in mx_records:
            try:
                host = mx.split()[-1].strip('.')
                a_mx = dns.resolver.resolve(host, 'A', lifetime=3.0)
                for r in a_mx: ips.add(r.to_text())
            except Exception: pass
            
        return list(ips)

    def check_ip_dnsbl(self, ip: str, zone: str, timeout_ms: int = 3000) -> Dict:
        import time
        start = time.time()
        timeout = timeout_ms / 1000.0
        
        # Reverse IP
        parts = ip.split('.')
        if len(parts) != 4:
            return {"status": "ERROR", "is_listed": False, "is_confirmed": False, "response_time_ms": 0}
            
        reversed_ip = ".".join(reversed(parts))
        query = f"{reversed_ip}.{zone}"
        
        try:
            answers = dns.resolver.resolve(query, 'A', lifetime=timeout)
            if answers:
                return {"status": "LISTED", "is_listed": True, "is_confirmed": True, "response_time_ms": int((time.time()-start)*1000)}
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return {"status": "CLEAN", "is_listed": False, "is_confirmed": False, "response_time_ms": int((time.time()-start)*1000)}
        except dns.exception.Timeout:
            return {"status": "TIMEOUT", "is_listed": False, "is_confirmed": False, "response_time_ms": None}
        except Exception:
            pass
            
        return {"status": "ERROR", "is_listed": False, "is_confirmed": False, "response_time_ms": int((time.time()-start)*1000)}

    def check_domain_dbl(self, domain: str, zone: str, timeout_ms: int = 3000) -> Dict:
        import time
        start = time.time()
        timeout = timeout_ms / 1000.0
        query = f"{domain}.{zone}"
        
        try:
            answers = dns.resolver.resolve(query, 'A', lifetime=timeout)
            if answers:
                return {"status": "LISTED", "is_listed": True, "is_confirmed": True, "response_time_ms": int((time.time()-start)*1000)}
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return {"status": "CLEAN", "is_listed": False, "is_confirmed": False, "response_time_ms": int((time.time()-start)*1000)}
        except dns.exception.Timeout:
            return {"status": "TIMEOUT", "is_listed": False, "is_confirmed": False, "response_time_ms": None}
        except Exception:
            pass
            
        return {"status": "ERROR", "is_listed": False, "is_confirmed": False, "response_time_ms": int((time.time()-start)*1000)}

    def check_dnssec(self, domain: str) -> str:
        try:
            req = dns.message.make_query(domain, dns.rdatatype.A, want_dnssec=True)
            nameservers = self.resolver.nameservers
            if not nameservers:
                return "UNKNOWN"
            res = dns.query.udp(req, nameservers[0], timeout=3)
            if res.flags & dns.flags.AD:
                return "PASS"
            return "FAIL"
        except Exception:
            return "UNKNOWN"

    def check_mta_sts(self, domain: str) -> str:
        records = self._safe_resolve(f"_mta-sts.{domain}", "TXT")
        for r in records:
            if r.startswith("v=STSv1"):
                return "PASS"
        return "FAIL"

    def check_tls_rpt(self, domain: str) -> str:
        records = self._safe_resolve(f"_smtp._tls.{domain}", "TXT")
        for r in records:
            if r.startswith("v=TLSRPTv1"):
                return "PASS"
        return "FAIL"

    def check_bimi(self, domain: str) -> str:
        records = self._safe_resolve(f"default._bimi.{domain}", "TXT")
        for r in records:
            if r.startswith("v=BIMI1"):
                return "PASS"
        return "FAIL"

    def _check_single_blacklist(self, reversed_ip: str, bl: str) -> bool:
        """Check one blacklist. Returns True if listed (bad)."""
        try:
            self.resolver.resolve(f"{reversed_ip}.{bl}", "A")
            return True
        except Exception:
            return False

    def check_blacklists(self, domain: str) -> str:
        """Check blacklists in parallel."""
        bls = ["zen.spamhaus.org", "bl.spamcop.net", "b.barracudacentral.org"]
        ips = self.get_a(domain)
        if not ips:
            return "UNKNOWN"
        reversed_ip = ".".join(reversed(ips[0].split(".")))
        
        futures = {_executor.submit(self._check_single_blacklist, reversed_ip, bl): bl for bl in bls}
        for future in as_completed(futures, timeout=6):
            try:
                if future.result():
                    return "FAIL"
            except Exception:
                pass
        return "PASS"

    def check_smtp(self, domain: str, receives_inbound_mail: bool = True) -> Dict[str, str]:
        """SMTP check respecting inbound configs."""
        mx_records = self.get_mx(domain)
        if not mx_records:
            return {"smtp_status": "FAIL", "tls_status": "UNKNOWN"}
        
        try:
            mx_list = [(int(r.split()[0]), r.split()[1]) for r in mx_records if len(r.split()) == 2]
            mx_list.sort(key=lambda x: x[0])
            mx_host = mx_list[0][1].strip('.')
        except Exception:
            mx_host = mx_records[0].split()[-1].strip('.')

        smtp_status = "UNKNOWN"
        tls_status = "UNKNOWN"

        port = 587 # Forced for testing

        try:
            sock = socket.create_connection((mx_host, port), timeout=3)
            smtp_status = "PASS"
            # Read banner
            data = sock.recv(1024).decode('utf-8', errors='ignore')
            # Send EHLO
            sock.sendall(b"EHLO healthcheck\r\n")
            data = sock.recv(1024).decode('utf-8', errors='ignore')
            if "STARTTLS" in data:
                tls_status = "PASS"
            else:
                tls_status = "FAIL"
            sock.sendall(b"QUIT\r\n")
            sock.close()
        except Exception:
            if receives_inbound_mail:
                smtp_status = "FAIL"
            else:
                smtp_status = "UNKNOWN"
            
        return {"smtp_status": smtp_status, "tls_status": tls_status}

    def run_all(self, domain: str) -> Dict:
        """Run all basic DNS record lookups. SPF/DKIM/DMARC run separately in check_all_domains."""
        # Fetch base records in parallel
        record_types = {"a": "A", "aaaa": "AAAA", "mx": "MX", "txt": "TXT", "ns": "NS", "cname": "CNAME"}
        results = {}
        futures = {_executor.submit(self._safe_resolve, domain, rdtype): key 
                   for key, rdtype in record_types.items()}
        
        for future in as_completed(futures, timeout=8):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception:
                results[key] = []
        
        # Ensure all keys present
        for key in record_types:
            results.setdefault(key, [])
        
        # SPF uses already-fetched TXT records (no extra query)
        results["spf_status"] = self.check_spf(results["txt"])
        results["dmarc_status"] = self.check_dmarc(domain)
        results["dkim_status"] = self.check_dkim(domain)
        
        return results
