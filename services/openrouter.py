import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class OpenRouterAI:
    """Calls OpenRouter free models to generate AI-powered recommendations."""
    
    def __init__(self, api_key: Optional[str], model: str = "meta-llama/llama-3.1-8b-instruct:free"):
        self.api_key = api_key or ""
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.timeout = httpx.Timeout(30.0)
    
    @property
    def available(self) -> bool:
        return bool(self.api_key)
    
    async def generate_recommendation(self, domain: str, checks: dict) -> str:
        """Generate an AI recommendation based on domain health check results."""
        if not self.available:
            return ""
        
        prompt = f"""You are an email deliverability expert. Analyze these DNS health check results for the domain "{domain}" and give a brief, actionable recommendation (2-3 sentences max).

Check Results:
- MX Records: {checks.get('mx_health', 'UNKNOWN')}
- SPF: {checks.get('spf_status', 'UNKNOWN')}
- DKIM: {checks.get('dkim_status', 'UNKNOWN')}
- DMARC: {checks.get('dmarc_status', 'UNKNOWN')}
- DNSSEC: {checks.get('dnssec_status', 'UNKNOWN')}
- Blacklist: {checks.get('blacklist_status', 'UNKNOWN')}
- SMTP: {checks.get('smtp_status', 'UNKNOWN')}
- MTA-STS: {checks.get('mta_sts_status', 'UNKNOWN')}
- BIMI: {checks.get('bimi_status', 'UNKNOWN')}

Focus on what's FAILING or WARNING. Be specific and concise."""

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost:8000",
                        "X-Title": "Mailforge Health Dashboard"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ],
                        "max_tokens": 200,
                        "temperature": 0.3
                    }
                )
                response.raise_for_status()
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                logger.info(f"OpenRouter AI recommendation generated for {domain}")
                return content.strip()
        except Exception as e:
            logger.error(f"OpenRouter AI error for {domain}: {e}")
            return ""

    async def generate_issue_recommendation(self, issue_type: str, domain: str, description: str) -> str:
        """Generate a specific fix recommendation for an issue."""
        if not self.available:
            return self._fallback_recommendation(issue_type)
        
        prompt = f"""You are an email infrastructure expert. Give a specific, actionable fix for this issue in 1-2 sentences:

Domain: {domain}
Issue Type: {issue_type}
Description: {description}

Be specific with DNS record examples where possible."""

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost:8000",
                        "X-Title": "Mailforge Health Dashboard"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ],
                        "max_tokens": 150,
                        "temperature": 0.3
                    }
                )
                response.raise_for_status()
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return content.strip()
        except Exception as e:
            logger.error(f"OpenRouter AI error: {e}")
            return self._fallback_recommendation(issue_type)
    
    def _fallback_recommendation(self, issue_type: str) -> str:
        """Static fallback recommendations when AI is unavailable."""
        fallbacks = {
            "SPF": "Publish an SPF record: v=spf1 include:_spf.mailforge.ai ~all",
            "DKIM": "Configure DKIM signing and publish DKIM DNS records for your domain.",
            "DMARC": "Publish a DMARC record: v=DMARC1; p=quarantine; rua=mailto:dmarc@yourdomain.com",
            "MX": "Configure MX records pointing to your mail server.",
            "BLACKLIST": "Check blacklist listings and submit delisting requests.",
            "SMTP": "Verify SMTP server is running and accessible on port 25.",
        }
        return fallbacks.get(issue_type, "Review and fix the configuration.")
