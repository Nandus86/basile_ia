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

    async def post_to_agent(self, webhook_path: str, payload: dict) -> dict:
        """Posts a ProcessRequest directly to the Basile /webhook/process endpoint.
        The payload must include agent_id and session_id.
        Retries 3 times on failure."""
        url = "/webhook/process"
        max_retries = 3
        backoff = 2.0
        
        for attempt in range(max_retries):
            try:
                # Disparador sends it transparently as the user would.
                resp = await self.client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError as e:
                logger.error(f"Error calling Basile agent on {url} (Attempt {attempt+1}/{max_retries}): {str(e)}")
                if attempt == max_retries - 1:
                    raise Exception(f"Failed to communicate with Basile Agent after {max_retries} attempts: {str(e)}")
                await asyncio.sleep(backoff)
                backoff *= 2

basile_client = BasileClient()
