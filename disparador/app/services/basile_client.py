import httpx
import logging
import asyncio

from app.config import settings

logger = logging.getLogger(__name__)

class BasileClient:
    def __init__(self):
        self.base_url = settings.BASILE_API_URL
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=120.0
        )

    async def close(self):
        await self.client.aclose()

    async def post_to_agent(self, webhook_path: str, payload: dict, custom_url: str = None) -> dict:
        """Posts a ProcessRequest to the Basile agent.
        If custom_url is provided and starts with http, it posts to that exact URL.
        Otherwise it uses the base_url + custom_url (or default /webhook/process).
        Retries 3 times on failure."""
        
        endpoint = custom_url if custom_url else "/webhook/process"
        
        # If custom_url is a full URL, we need to use a clean post (without base_url prepended by self.client)
        # However, httpx.AsyncClient(base_url=...) will PREPEND base_url if the path starts with /.
        # If we pass a full URL to self.client.post, it might error or behave unexpectedly depending on httpx version.
        # To be safe, if endpoint starts with http, we use a temporary client or check if we can override.
        
        max_retries = 3
        backoff = 2.0
        
        for attempt in range(max_retries):
            try:
                if endpoint.startswith("http"):
                    async with httpx.AsyncClient(timeout=120.0) as tmp_client:
                        resp = await tmp_client.post(endpoint, json=payload)
                        resp.raise_for_status()
                        return resp.json()
                else:
                    # Uses self.client with configured base_url
                    resp = await self.client.post(endpoint, json=payload)
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPError as e:
                logger.error(f"Error calling target {endpoint} (Attempt {attempt+1}/{max_retries}): {str(e)}")
                if attempt == max_retries - 1:
                    raise Exception(f"Failed after {max_retries} attempts: {str(e)}")
                await asyncio.sleep(backoff)
                backoff *= 2

basile_client = BasileClient()
