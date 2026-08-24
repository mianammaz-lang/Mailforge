import dns.resolver

def test_dnsbl(ip, zone):
    reversed_ip = ".".join(reversed(ip.split(".")))
    query = f"{reversed_ip}.{zone}"
    try:
        answers = dns.resolver.resolve(query, 'A', lifetime=2.0)
        return f"LISTED ({answers[0]})"
    except dns.resolver.NXDOMAIN:
        return "CLEAN"
    except Exception as e:
        return f"ERROR ({type(e).__name__})"

def test_dbl(domain, zone):
    query = f"{domain}.{zone}"
    try:
        answers = dns.resolver.resolve(query, 'A', lifetime=2.0)
        return f"LISTED ({answers[0]})"
    except dns.resolver.NXDOMAIN:
        return "CLEAN"
    except Exception as e:
        return f"ERROR ({type(e).__name__})"

# Test clean IP (Google DNS)
test_ip = "8.8.8.8"
print("Spamhaus ZEN:", test_dnsbl(test_ip, "zen.spamhaus.org"))
print("SpamCop:", test_dnsbl(test_ip, "bl.spamcop.net"))
print("Barracuda:", test_dnsbl(test_ip, "b.barracudacentral.org"))
print("PSBL:", test_dnsbl(test_ip, "psbl.surriel.com"))
print("Spamhaus DBL (domain):", test_dbl("google.com", "dbl.spamhaus.org"))

# Test test IP (127.0.0.2 is often a test listed IP for spamhaus)
test_ip = "127.0.0.2"
print("TEST Spamhaus ZEN:", test_dnsbl(test_ip, "zen.spamhaus.org"))
print("TEST SpamCop:", test_dnsbl(test_ip, "bl.spamcop.net"))
print("TEST Barracuda:", test_dnsbl(test_ip, "b.barracudacentral.org"))
