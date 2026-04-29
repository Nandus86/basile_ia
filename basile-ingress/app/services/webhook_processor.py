"""
Webhook Processor - Normalizes incoming webhooks based on pipeline schema
"""
from typing import Dict, Any, Optional
import uuid


def get_nested_value(data: dict, path: str) -> Any:
    """Get nested value using dot notation or direct key"""
    if "." in path:
        keys = path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value
    # If not using dot notation, try direct key
    if path in data:
        return data[path]
    # Fallback to check if it's wrapped in 'body'
    if "body" in data and isinstance(data["body"], dict) and path in data["body"]:
        return data["body"][path]
    return None


def set_nested_value(data: dict, path: str, value: Any) -> None:
    """Set nested value using dot notation"""
    if "." in path:
        keys = path.split(".")
        current = data
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
    else:
        data[path] = value


def normalize_webhook_payload(
    payload: Dict[str, Any],
    input_schema: Dict[str, Any],
    pipeline_path: str
) -> Dict[str, Any]:
    """
    Normalize incoming webhook payload based on input_schema mappings.
    
    Returns normalized dict with:
    - message: the message text
    - session_id: session identifier
    - agent_id: optional agent ID
    - user_access_level: optional access level
    - context_data: additional context
    - transition_data: metadata
    - job_id: unique job ID
    """
    mappings = input_schema.get("mappings", {})
    defaults = input_schema.get("defaults", {})
    message_required = input_schema.get("messageRequired", True)
    session_id_field = input_schema.get("sessionIdField", "session_id")
    
    normalized = {
        "job_id": f"job_{uuid.uuid4().hex}",
        "pipeline_path": pipeline_path,
    }
    
    context_data = {}
    transition_data = {}
    
    for external_field, internal_field in mappings.items():
        value = get_nested_value(payload, external_field)
        if value is not None:
            if internal_field.startswith("context_data."):
                context_key = internal_field.replace("context_data.", "")
                context_data[context_key] = value
            elif internal_field.startswith("transition_data."):
                trans_key = internal_field.replace("transition_data.", "")
                transition_data[trans_key] = value
            else:
                normalized[internal_field] = value
    
    for key, default_value in defaults.items():
        if key not in normalized:
            normalized[key] = default_value
    
    if "session_id" not in normalized:
        session_value = get_nested_value(payload, session_id_field)
        if session_value:
            normalized["session_id"] = session_value
        else:
            normalized["session_id"] = f"session_{uuid.uuid4().hex[:8]}"
    
    if "message" not in normalized:
        message_value = get_nested_value(payload, "message")
        if message_value is not None:
            normalized["message"] = message_value
        elif message_required:
            raise ValueError("message is required but not found in payload")
        else:
            normalized["message"] = ""
    
    if context_data:
        normalized["context_data"] = context_data
    if transition_data:
        normalized["transition_data"] = transition_data
    
    return normalized


def validate_pipeline_auth(
    pipeline_auth_type: str,
    pipeline_auth_token: Optional[str],
    api_key: Optional[str]
) -> bool:
    """Validate authentication for pipeline"""
    if pipeline_auth_type == "none":
        return True
    
    if pipeline_auth_type == "api_key":
        return api_key == pipeline_auth_token
    
    return False