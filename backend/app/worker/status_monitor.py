import asyncio
import time
import httpx
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger("app.worker.status_monitor")

class StatusMonitor:
    def __init__(
        self, 
        callback_url: Optional[str], 
        agent_config: Dict[str, Any],
        session_id: str,
        start_time: Optional[float] = None
    ):
        self.callback_url = callback_url
        self.agent_config = agent_config
        self.session_id = session_id
        self.start_time = start_time or time.time()
        self.is_running = False
        self.task = None
        self.progress_log: List[str] = []
        
        # Extract config
        self.enabled = agent_config.get("status_updates_enabled", False)
        self.config = agent_config.get("status_updates_config", {}) or {}
        
        # Keys aligned with frontend (Agents.vue status_updates_config)
        self.initial_delay = float(self.config.get("initial_delay_seconds", 5))
        self.initial_msg = self.config.get("initial_message", "Aguarde um momentinho, estou processando sua solicitacao...")
        self.follow_up_interval = float(self.config.get("follow_up_interval_seconds", 10))
        self.follow_up_msg = self.config.get("follow_up_message", "Ainda estou trabalhando nisso, ja estou quase terminando...")
        self.max_updates = int(self.config.get("max_updates", 3))

    async def start(self):
        if not self.enabled or not self.callback_url:
            return
        
        self.is_running = True
        self.task = asyncio.create_task(self._run_loop())
        logger.info(f"StatusMonitor started for session {self.session_id} (max_updates={self.max_updates})")

    async def stop(self):
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info(f"StatusMonitor stopped for session {self.session_id}")

    def log_progress(self, message: str):
        """Log a step of progress to be included in future status updates"""
        timestamp = time.strftime("%H:%M:%S")
        self.progress_log.append(f"[{timestamp}] {message}")
        logger.info(f"Progress log: {message}")

    async def _run_loop(self):
        try:
            sent_count = 0
            
            while self.is_running and sent_count < self.max_updates:
                elapsed = time.time() - self.start_time
                
                # Calculate when the next message should be sent
                if sent_count == 0:
                    next_delay = self.initial_delay
                else:
                    next_delay = self.initial_delay + (sent_count * self.follow_up_interval)
                
                if elapsed >= next_delay:
                    # Choose message based on count
                    if sent_count == 0:
                        text = self.initial_msg
                    else:
                        text = self.follow_up_msg
                        # Include progress summary for follow-ups
                        summary = "\n".join(self.progress_log[-3:]) if self.progress_log else ""
                        if summary:
                            text += f"\n\nO que ja fiz:\n{summary}"
                    
                    await self._send_status(text)
                    sent_count += 1
                    logger.info(f"StatusMonitor sent message {sent_count}/{self.max_updates} for session {self.session_id}")
                
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in StatusMonitor loop: {e}")

    async def _send_status(self, text: str):
        if not self.callback_url:
            return
            
        payload = {
            "status": "processing",
            "session_id": self.session_id,
            "response": text,
            "is_interim": True
        }
        
        try:
            async with httpx.AsyncClient() as client:
                await client.post(self.callback_url, json=payload, timeout=5.0)
                logger.info(f"Interim status sent to {self.callback_url}: {text[:50]}...")
        except Exception as e:
            logger.error(f"Failed to send status update: {e}")
