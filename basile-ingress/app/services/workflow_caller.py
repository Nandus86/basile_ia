"""
Workflow Caller — Executes workflows on the main backend before forwarding
"""
import httpx
import logging
from typing import Dict, Any, Optional, Tuple

from app.config import settings

logger = logging.getLogger("basile-ingress.workflow_caller")


class WorkflowCaller:
    """
    Calls the main Basile backend to execute a workflow synchronously.
    Used by the Ingress webhook handler to run automations before
    forwarding the payload to the destination URL.
    """

    def __init__(self):
        self.base_url = settings.BACKEND_API_URL
        self.timeout = settings.WORKFLOW_TIMEOUT

    async def execute(
        self,
        workflow_id: str,
        payload: Dict[str, Any],
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Execute a workflow synchronously on the backend.

        Args:
            workflow_id: UUID of the workflow to execute
            payload: The normalized payload to send as trigger_data

        Returns:
            (success, result_data, error_message)
        """
        url = f"{self.base_url}/workflows/{workflow_id}/execute"
        body = {"trigger_data": payload}

        logger.info(
            f"[WorkflowCaller] Executing workflow {workflow_id} "
            f"at {url}"
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    url,
                    json=body,
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code < 400:
                    data = response.json()
                    status = data.get("status", "unknown")

                    if status == "completed":
                        result = data.get("result") or data.get("context", {})
                        logger.info(
                            f"[WorkflowCaller] ✅ Workflow {workflow_id} "
                            f"completed successfully"
                        )
                        return True, result, None
                    elif status == "failed":
                        error_msg = data.get("error_message", "Workflow failed")
                        logger.error(
                            f"[WorkflowCaller] ❌ Workflow {workflow_id} "
                            f"failed: {error_msg}"
                        )
                        return False, None, error_msg
                    else:
                        # paused or other status
                        logger.warning(
                            f"[WorkflowCaller] ⚠️ Workflow {workflow_id} "
                            f"returned status '{status}'"
                        )
                        result = data.get("result") or data.get("context", {})
                        return True, result, None

                error_msg = (
                    f"HTTP {response.status_code}: "
                    f"{response.text[:300]}"
                )
                logger.error(
                    f"[WorkflowCaller] ❌ Workflow {workflow_id} "
                    f"HTTP error: {error_msg}"
                )
                return False, None, error_msg

            except httpx.ConnectError:
                msg = "Backend service unavailable (connection refused)"
                logger.error(f"[WorkflowCaller] {msg}")
                return False, None, msg
            except httpx.TimeoutException:
                msg = f"Workflow execution timed out ({self.timeout}s)"
                logger.error(f"[WorkflowCaller] {msg}")
                return False, None, msg
            except Exception as e:
                msg = f"Unexpected error: {str(e)}"
                logger.error(f"[WorkflowCaller] {msg}")
                return False, None, msg

    async def list_workflows(self) -> Tuple[bool, Optional[list], Optional[str]]:
        """
        List all available workflows from the backend.
        Used by the proxy endpoint for the frontend dropdown.

        Returns:
            (success, workflows_list, error_message)
        """
        url = f"{self.base_url}/workflows"

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.get(url)
                if response.status_code < 400:
                    data = response.json()
                    workflows = data.get("workflows", [])
                    return True, workflows, None

                return False, None, f"HTTP {response.status_code}"
            except Exception as e:
                return False, None, str(e)


workflow_caller = WorkflowCaller()
