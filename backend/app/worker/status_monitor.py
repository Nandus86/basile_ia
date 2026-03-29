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
        start_time: Optional[float] = None,
        transition_data: Optional[Dict[str, Any]] = None,
        is_structured: bool = False
    ):
        self.callback_url = callback_url
        self.agent_config = agent_config
        self.session_id = session_id
        self.start_time = start_time or time.time()
        self.transition_data = transition_data
        self.is_structured = is_structured
        self.is_running = False
        self.task = None
        self.progress_log: List[str] = []
        self.current_moment = "processando sua solicitação"

        # Extract config
        self.enabled = agent_config.get("status_updates_enabled", False)
        self.config = agent_config.get("status_updates_config", {}) or {}

        # Keys aligned with frontend (Agents.vue status_updates_config)
        self.initial_delay = float(self.config.get("initial_delay_seconds", 2))
        self.initial_msg = self.config.get("initial_message", "Aguarde um momentinho, estou processando sua solicitacao...")
        self.follow_up_interval = float(self.config.get("follow_up_interval_seconds", 7))
        self.follow_up_msg = self.config.get("follow_up_message", "Ainda estou trabalhando nisso, ja estou quase terminando...")
        self.max_updates = int(self.config.get("max_updates", 3))

    async def start(self):
        if not self.callback_url:
            return

        self.is_running = True
        self.task = asyncio.create_task(self._run_loop())
        logger.info(f"StatusMonitor started for session {self.session_id} (enabled={self.enabled}, max_updates={self.max_updates})")

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
        """Log a step of progress and update current_moment"""
        timestamp = time.strftime("%H:%M:%S")
        self.progress_log.append(f"[{timestamp}] {message}")
        # Automatically update current_moment with a cleaned version of the progress
        # Limit to 100 chars as requested
        self.current_moment = message[:100].lower().strip(".")
        logger.info(f"Progress log: {message}")

    async def _run_loop(self):
        try:
            sent_count = 0
            # If status_updates_enabled is False, only send up to 1 (initial) if enough time passes
            max_msgs = self.max_updates if self.enabled else 1

            while self.is_running and sent_count < max_msgs:
                await asyncio.sleep(1) # Check every second
                elapsed = time.time() - self.start_time

                # Calculate when the next message should be sent
                if sent_count == 0:
                    target_time = self.initial_delay
                else:
                    target_time = self.initial_delay + (sent_count * self.follow_up_interval)

                if elapsed >= target_time:
                    # Choose message based on count
                    if sent_count == 0:
                        text = self.initial_msg
                    else:
                        text = self.follow_up_msg
                    
                    # 1. Replace {{ $show_moment }} with current status
                    if "{{ $show_moment }}" in text:
                        text = text.replace("{{ $show_moment }}", self.current_moment)
                    
                    # 2. Traditional summary if no placeholder was used and enabled
                    elif self.enabled and self.progress_log:
                        summary = "\n".join(self.progress_log[-3:])
                        text += f"\n\nO que ja fiz:\n{summary}"

                    await self._send_status(text)
                    sent_count += 1
                    logger.info(f"StatusMonitor sent message {sent_count}/{max_msgs} for session {self.session_id}")

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
            "is_interim": True,
            "transition_data": self.transition_data
        }

        # Select response key based on agent type
        if self.is_structured:
            payload["output"] = text
        else:
            payload["response"] = text

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.callback_url, json=payload, timeout=10.0)
                logger.info(f"Interim status sent to {self.callback_url}: {text[:50]}... (HTTP {resp.status_code})")
        except httpx.TimeoutException:
            logger.error(f"Timeout sending status update to {self.callback_url}")
        except httpx.ConnectError as e:
            logger.error(f"Connection error sending status update to {self.callback_url}: {e}")
        except Exception as e:
            logger.error(f"Failed to send status update to {self.callback_url}: {e}")
