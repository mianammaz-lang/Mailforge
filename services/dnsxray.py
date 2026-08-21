from typing import Dict
class DNSXrayProvider:
    def __init__(self, api_key: str):
        self.api_key = api_key
    async def check_domain(self, domain: str) -> Dict:
        if not self.api_key:
            return {"provider": "dnsxray", "status": "unavailable"}
        return {"provider": "dnsxray", "status": "ok", "data": {}}
