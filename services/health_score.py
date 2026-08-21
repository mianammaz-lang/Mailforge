from typing import Dict

def calculate_domain_score(checks: Dict) -> float:
    weights = {
        "mx_status": 10,
        "spf_status": 15,
        "dkim_status": 15,
        "dmarc_status": 15,
        "blacklist_status": 15,
        "dnssec_status": 10,
        "mta_sts_status": 5,
        "tls_status": 5,
        "bimi_status": 5,
        "smtp_status": 5
    }
    
    total_weight = 0
    earned = 0
    
    for key, weight in weights.items():
        status = checks.get(key, "UNKNOWN")
        if status != "UNKNOWN":
            total_weight += weight
            if status == "PASS":
                earned += weight
            elif status == "WARN":
                earned += weight * 0.5
                
    if total_weight == 0:
        return 0.0
    return (earned / total_weight) * 100.0

def calculate_mailbox_score(domain_score: float, checks: Dict, status: str) -> float:
    weights = {
        "mailforge_status": 20,
        "domain_health": 20,
        "mx_status": 10,
        "spf_status": 10,
        "dkim_status": 10,
        "dmarc_status": 10,
        "smtp_connectivity": 10,
        "mailbox_verification": 10
    }
    
    total_weight = 0
    earned = 0
    
    # Mailforge status
    total_weight += weights["mailforge_status"]
    if status.lower() == "active":
        earned += weights["mailforge_status"]
        
    # Domain health
    total_weight += weights["domain_health"]
    earned += weights["domain_health"] * (domain_score / 100.0)
    
    for key in ["mx_status", "spf_status", "dkim_status", "dmarc_status", "smtp_connectivity", "mailbox_verification"]:
        val = checks.get(key, "UNKNOWN")
        if val != "UNKNOWN":
            total_weight += weights[key]
            if val == "PASS":
                earned += weights[key]
            elif val == "WARN":
                earned += weights[key] * 0.5
                
    if total_weight == 0:
        return 0.0
    return (earned / total_weight) * 100.0

def get_health_category(score: float) -> str:
    if score >= 90: return "HEALTHY"
    if score >= 75: return "GOOD"
    if score >= 60: return "WARNING"
    return "CRITICAL"
