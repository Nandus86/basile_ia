"""
HTTP Forwarder - Forwards normalized payloads to target services
"""
import httpx
from typing import Dict, Any, Optional, Tuple

from app.config import settings


class HttpForwarder:
    def __init__(self):
        self.timeout = settings.FORWARD_TIMEOUT

    async def forward(
        self,
        url: str,
        payload: Dict[str, Any],
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        Forward payload to target URL.
        Returns: (success, response_data, error_message)
        """
        default_headers = {
            "Content-Type": "application/json",
            "User-Agent": "basile-ingress/1.0",
        }
        if headers:
            default_headers.update(headers)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.request(
                    method.upper(), url, json=payload, headers=default_headers
                )
                if response.status_code < 400:
                    try:
                        return True, response.json(), None
                    except Exception:
                        return True, {"raw": response.text[:500]}, None
                return False, None, f"HTTP {response.status_code}: {response.text[:200]}"

            except httpx.ConnectError:
                return False, None, "Service unavailable (connection refused)"
            except httpx.TimeoutException:
                return False, None, "Request timeout"
            except Exception as e:
                return False, None, f"Unexpected error: {str(e)}"

    async def check_health(self, base_url: str) -> bool:
        """Check if target service is reachable"""
        try:
            # Strip path to get base, append /health
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            health_url = f"{parsed.scheme}://{parsed.netloc}/health"
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(health_url)
                return resp.status_code < 400
        except Exception:
            return False


forwarder = HttpForwarder()
