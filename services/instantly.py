import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class InstantlyClient:
    def __init__(self, api_key: Optional[str]):
        self.base_url = "https://api.instantly.ai/api/v2"
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        } if api_key else {}

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def list_tests(self) -> list:
        if not self.available:
            return []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(f"{self.base_url}/inbox-placement-tests", headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error listing Instantly tests: {e}")
            return []

    async def get_analytics(self) -> list:
        if not self.available:
            return []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(f"{self.base_url}/inbox-placement-analytics", headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error getting Instantly analytics: {e}")
            return []

    async def get_test_stats(self, test_id: str) -> dict:
        if not self.available:
            return {}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{self.base_url}/inbox-placement-analytics/stats-by-test-id",
                    headers=self.headers,
                    json={"test_id": test_id}
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error getting Instantly test stats for {test_id}: {e}")
            return {}

    async def get_deliverability_insights(self) -> dict:
        if not self.available:
            return {}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{self.base_url}/inbox-placement-analytics/deliverability-insights",
                    headers=self.headers,
                    json={}
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error getting Instantly deliverability insights: {e}")
            return {}
