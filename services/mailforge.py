import httpx
from typing import List, Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)

class MailforgeClient:
    def __init__(self, api_key: str):
        self.api_key = api_key or ""
        self.base_url = "https://api.mailforge.ai/public"
        self.headers = {
            "Authorization": self.api_key,
            "Accept": "application/json"
        }
        self.timeout = httpx.Timeout(30.0)
        
    async def _request(self, method: str, endpoint: str, params: Optional[Dict] = None) -> Any:
        if not self.api_key:
            logger.warning("Mailforge API key not configured")
            return {"error": "API key not configured", "status": "ERROR"}
            
        url = f"{self.base_url}{endpoint}"
        logger.info(f"Mailforge request: {method} {url} params={params}")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(method, url, headers=self.headers, params=params)
                response.raise_for_status()
                result = response.json()
                logger.info(f"Mailforge response type: {type(result).__name__}, preview: {str(result)[:500]}")
                return result
        except httpx.HTTPStatusError as e:
            logger.error(f"Mailforge HTTP Error: {e.response.status_code} - {e.response.text}")
            return {"error": str(e), "status": "ERROR"}
        except Exception as e:
            logger.error(f"Mailforge Request Error: {str(e)}")
            return {"error": str(e), "status": "ERROR"}

    def _extract_list(self, data: Any) -> List[Dict]:
        """Extract a list of items from whatever shape the API returns."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if "error" in data:
                return []
            # Try common wrapper keys
            for key in ("data", "domains", "mailboxes", "items", "results"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            # If the dict itself looks like a single item, wrap it
            if "id" in data or "name" in data or "email" in data:
                return [data]
        return []

    async def get_workspaces(self) -> List[Dict]:
        data = await self._request("GET", "/workspaces")
        return self._extract_list(data)

    async def get_domains(self) -> List[Dict]:
        data = await self._request("GET", "/domains")
        return self._extract_list(data)

    async def get_mailboxes(self) -> List[Dict]:
        data = await self._request("GET", "/mailboxes")
        return self._extract_list(data)

    async def get_domain_dns(self, domain_id: str) -> Dict:
        data = await self._request("GET", f"/domains/{domain_id}/dns")
        if isinstance(data, dict) and "error" not in data:
            return data
        return {}
