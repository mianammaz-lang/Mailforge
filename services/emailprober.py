from typing import Dict
class EmailProberProvider:
    def __init__(self, api_key: str):
        self.api_key = api_key
    async def verify_mailbox(self, email: str) -> Dict:
        if not self.api_key:
            return {"provider": "emailprober", "status": "unavailable"}
        return {"provider": "emailprober", "status": "ok", "data": {}}
