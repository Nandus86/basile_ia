"""
Webhook Sender - Sends transformed results to external webhooks with retry
"""
import asyncio
import httpx
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from app.config import settings


class WebhookSender:
    def __init__(self):
        self.timeout = settings.DEFAULT_WEBHOOK_TIMEOUT
    
    async def send_with_retry(
        self,
        url: str,
        data: Dict[str, Any],
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None,
        retry_config: Optional[Dict[str, Any]] = None
    ) -> tuple[bool, Optional[str], int]:
        """
        Send webhook with exponential backoff retry.
        
        Returns: (success, error_message, attempts)
        """
        max_retries = retry_config.get("maxRetries", settings.DEFAULT_RETRY_MAX) if retry_config else settings.DEFAULT_RETRY_MAX
        delays = retry_config.get("delays", settings.DEFAULT_RETRY_DELAYS) if retry_config else settings.DEFAULT_RETRY_DELAYS
        
        default_headers = {
            "Content-Type": "application/json",
            "User-Agent": "basile-egress/1.0",
        }
        if headers:
            default_headers.update(headers)
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(max_retries):
                try:
                    if method.upper() == "POST":
                        response = await client.post(url, json=data, headers=default_headers)
                    elif method.upper() == "PUT":
                        response = await client.put(url, json=data, headers=default_headers)
                    else:
                        response = await client.request(method, url, json=data, headers=default_headers)
                    
                    if response.status_code < 400:
                        return True, None, attempt + 1
                    
                    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                    
                except httpx.TimeoutException:
                    error_msg = "Request timeout"
                except httpx.RequestError as e:
                    error_msg = f"Request error: {str(e)}"
                except Exception as e:
                    error_msg = f"Unexpected error: {str(e)}"
                
                if attempt < max_retries - 1:
                    delay = delays[attempt] if attempt < len(delays) else delays[-1]
                    await asyncio.sleep(delay / 1000)
            
            return False, error_msg, max_retries
    
    async def send(
        self,
        url: str,
        data: Dict[str, Any],
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Send webhook without retry (single attempt).
        
        Returns: (success, error_message)
        """
        default_headers = {
            "Content-Type": "application/json",
            "User-Agent": "basile-egress/1.0",
        }
        if headers:
            default_headers.update(headers)
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                if method.upper() == "POST":
                    response = await client.post(url, json=data, headers=default_headers)
                elif method.upper() == "PUT":
                    response = await client.put(url, json=data, headers=default_headers)
                else:
                    response = await client.request(method, url, json=data, headers=default_headers)
                
                if response.status_code < 400:
                    return True, None
                
                return False, f"HTTP {response.status_code}: {response.text[:200]}"
            
            except Exception as e:
                return False, str(e)


webhook_sender = WebhookSender()