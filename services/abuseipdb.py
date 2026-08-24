import httpx
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class AbuseIPDBClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.base_url = "https://api.abuseipdb.com/api/v2"
        self.headers = {
            "Accept": "application/json",
            "Key": self.api_key
        }

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def check_ip(self, ip_address: str, max_age_days: int = 90) -> Dict[str, Any]:
        if not self.available:
            return {"provider": "AbuseIPDB", "confidence_score": 0, "risk": "UNKNOWN", "error": "API Key Missing"}

        url = f"{self.base_url}/check"
        params = {
            "ipAddress": ip_address,
            "maxAgeInDays": max_age_days
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=self.headers, params=params)
                
                if response.status_code == 200:
                    data = response.json().get("data", {})
                    score = data.get("abuseConfidenceScore", 0)
                    
                    risk = "LOW"
                    if score > 10: risk = "MODERATE"
                    if score > 30: risk = "ELEVATED"
                    if score > 60: risk = "HIGH"
                    
                    return {
                        "provider": "AbuseIPDB",
                        "ip": ip_address,
                        "confidence_score": score,
                        "risk": risk,
                        "total_reports": data.get("totalReports", 0),
                        "country": data.get("countryCode", ""),
                        "isp": data.get("isp", ""),
                        "domain": data.get("domain", ""),
                        "usage_type": data.get("usageType", ""),
                        "last_reported": data.get("lastReportedAt", "")
                    }
                elif response.status_code == 429:
                    return {"provider": "AbuseIPDB", "confidence_score": 0, "risk": "UNKNOWN", "error": "Rate Limited"}
                else:
                    logger.error(f"AbuseIPDB API Error: {response.status_code} {response.text}")
                    return {"provider": "AbuseIPDB", "confidence_score": 0, "risk": "UNKNOWN", "error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"AbuseIPDB connection error: {e}")
            return {"provider": "AbuseIPDB", "confidence_score": 0, "risk": "UNKNOWN", "error": "Connection Failed"}
