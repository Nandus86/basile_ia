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
        self.current_moments = ["processando sua solicitação"]
        self.current_moment = self.current_moments[0]

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
        # Support multiple variations separated by '|'
        parts = [p.strip()[:100].lower().strip(".") for p in message.split('|') if p.strip()]
        if parts:
            self.current_moments = parts
            self.current_moment = self.current_moments[0]
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
                    # Build status text
                    status_text = self.follow_up_msg if sent_count > 0 else self.initial_msg
                    
                    # Pick variation based on sent_count
                    if hasattr(self, 'current_moments') and self.current_moments:
                        idx = sent_count % len(self.current_moments)
                        moment_to_show = self.current_moments[idx]
                    else:
                        moment_to_show = self.current_moment
                        
                    status_text = status_text.replace("{{ $show_moment }}", moment_to_show)

                    await self._send_status(status_text)
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
            "transition_data": self.transition_data,
            "result": text  # Unified key for all types of agents (including structured)
        }

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
