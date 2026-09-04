import httpx
import logging
import asyncio

from app.config import settings

logger = logging.getLogger(__name__)

class BasileClient:
    def __init__(self):
        self.base_url = settings.BASILE_API_URL
        headers = {}
        if getattr(settings, "ADMIN_API_KEY", None):
            headers = {
                "Authorization": f"Bearer {settings.ADMIN_API_KEY}",
                "X-API-Key": settings.ADMIN_API_KEY
            }
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=120.0
        )

    async def close(self):
        await self.client.aclose()

    def _get_headers(self) -> dict:
        headers = {}
        if getattr(settings, "ADMIN_API_KEY", None):
            headers = {
                "Authorization": f"Bearer {settings.ADMIN_API_KEY}",
                "X-API-Key": settings.ADMIN_API_KEY
            }
        return headers

    async def post_to_agent(self, webhook_path: str, payload: dict, custom_url: str = None) -> dict:
        """Posts a ProcessRequest to the Basile agent.
        If custom_url is provided and starts with http, it posts to that exact URL.
        Otherwise it uses the base_url + custom_url (or default /webhook/process).
        Retries 3 times on failure."""
        
        endpoint = custom_url if custom_url else (webhook_path if webhook_path else "/webhook/process")
        
        try:
            if endpoint.startswith("http"):
                async with httpx.AsyncClient(timeout=120.0) as tmp_client:
                    resp = await tmp_client.post(endpoint, json=payload, headers=self._get_headers())
                    resp.raise_for_status()
                    return resp.json()
            else:
                # Uses self.client with configured base_url and headers
                resp = await self.client.post(endpoint, json=payload)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Error calling target {endpoint}: {str(e)}")
            raise Exception(f"Failed to call agent: {str(e)}")

basile_client = BasileClient()
