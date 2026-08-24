import httpx
import logging
from typing import Optional, Dict, List
import asyncio

logger = logging.getLogger(__name__)

class InstantlyClient:
    def __init__(self, api_key: Optional[str]):
        self.api_key = api_key
        self.base_url = "https://api.instantly.ai/api/v2"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    @property
    def available(self) -> bool:
        return bool(self.api_key)
        
    async def list_tests(self) -> List[Dict]:
        if not self.available:
            return []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{self.base_url}/inbox-placement-tests", headers=self.headers)
                resp.raise_for_status()
                data = resp.json()
                return data.get("items", data.get("data", []))
        except Exception as e:
            logger.error(f"Instantly list_tests error: {e}")
            return []

    async def get_analytics(self) -> List[Dict]:
        if not self.available:
            return []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{self.base_url}/inbox-placement-analytics", headers=self.headers)
                resp.raise_for_status()
                data = resp.json()
                return data.get("items", data.get("data", []))
        except Exception as e:
            logger.error(f"Instantly get_analytics error: {e}")
            return []

    async def create_test(self, name: str) -> Dict:
        if not self.available:
            return {}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                payload = {"name": name}
                resp = await client.post(f"{self.base_url}/inbox-placement-tests", json=payload, headers=self.headers)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"Instantly create_test error: {e}")
            return {}

    async def start_test(self, test_id: str) -> bool:
        if not self.available:
            return False
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(f"{self.base_url}/inbox-placement-tests/{test_id}/start", headers=self.headers)
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Instantly start_test error: {e}")
            return False

    async def get_test_stats(self, test_id: str) -> Dict:
        if not self.available:
            return {}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                payload = {"test_id": test_id}
                resp = await client.post(f"{self.base_url}/inbox-placement-analytics/stats-by-test-id", json=payload, headers=self.headers)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"Instantly get_test_stats error: {e}")
            return {}

    async def get_deliverability_insights(self) -> Dict:
        if not self.available:
            return {}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(f"{self.base_url}/inbox-placement-analytics/deliverability-insights", headers=self.headers)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"Instantly get_deliverability_insights error: {e}")
            return {}

    async def run_automated_inbox_test(self) -> Dict:
        """Finds or creates a test, runs it, and returns stats."""
        if not self.available:
            return {"status": "NOT_CONFIGURED", "error": "API Key missing"}
            
        tests = await self.list_tests()
        if not tests:
            test = await self.create_test(name=f"Automated Test {asyncio.get_event_loop().time()}")
            if not test:
                return {"status": "FAILED", "error": "Failed to create test"}
            test_id = test.get("id") or test.get("_id")
        else:
            test_id = tests[0].get("id") or tests[0].get("_id")
            
        if not test_id:
             return {"status": "FAILED", "error": "Could not identify test ID"}

        # Try to start it
        await self.start_test(test_id)
        
        # Poll for completion (simplified for demo, wait 10s)
        await asyncio.sleep(5)
        
        stats = await self.get_test_stats(test_id)
        return {
            "status": "COMPLETED",
            "test_id": test_id,
            "stats": stats
        }
