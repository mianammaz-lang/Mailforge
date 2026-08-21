from typing import Dict
class IntoDNSProvider:
    def __init__(self, api_key: str):
        self.api_key = api_key
    async def check_domain(self, domain: str) -> Dict:
        if not self.api_key:
            return {"provider": "intodns", "status": "unavailable"}
        return {"provider": "intodns", "status": "ok", "data": {}}
