from database.database import SessionLocal
from database.models import Domain, DomainCheck
import json

db = SessionLocal()
domain = db.query(Domain).filter(Domain.name == 'alsharqimail03.com').first()
if domain:
    check = domain.checks[-1]
    print(f"Blacklist Status: {check.blacklist_status}")
    print(f"Resolved IPs: {check.resolved_ips}")
    print(f"AbuseIPDB: {json.dumps(check.ip_reputation, indent=2)}")
    print(f"Blacklist Details: {json.dumps(check.blacklist_details, indent=2)}")
db.close()
