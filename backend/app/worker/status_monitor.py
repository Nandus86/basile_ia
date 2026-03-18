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
        start_time: float = None
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
        self.config = agent_config.get("status_updates_config", {})
        
        self.delay_1 = float(self.config.get("delay_1_seconds", 5))
        self.msg_1 = self.config.get("delay_1_message", "Aguarde um momentinho que estou validando...")
        
        self.delay_2 = float(self.config.get("delay_2_seconds", 15))
        self.msg_2 = self.config.get("delay_2_message", "Ainda estou processando, um momento...")

    async def start(self):
        if not self.enabled or not self.callback_url:
            return
        
        self.is_running = True
        self.task = asyncio.create_task(self._run_loop())
        logger.info(f"StatusMonitor started for session {self.session_id}")

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
            sent_1 = False
            sent_2 = False
            
            while self.is_running:
                elapsed = time.time() - self.start_time
                
                # Check first delay
                if not sent_1 and elapsed >= self.delay_1:
                    await self._send_status(self.msg_1)
                    sent_1 = True
                
                # Check second delay (relative to start)
                if not sent_2 and elapsed >= (self.delay_1 + self.delay_2):
                    # For second message, include progress summary
                    summary = "\n".join(self.progress_log[-3:]) if self.progress_log else ""
                    full_msg = self.msg_2
                    if summary:
                        full_msg += f"\n\nO que já fiz:\n{summary}"
                    
                    await self._send_status(full_msg)
                    sent_2 = True
                    # After second message, we stop sending automated ones to avoid spam
                    break
                
                await asyncio.sleep(1)
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
                logger.info(f"Interim status sent: {text[:50]}...")
        except Exception as e:
            logger.error(f"Failed to send status update: {e}")
