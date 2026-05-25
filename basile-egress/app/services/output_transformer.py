"""
Output Transformer - Maps result fields based on output_schema
"""
from typing import Dict, Any, Optional


def get_nested_value(data: dict, path: str) -> Any:
    """Get nested value using dot notation"""
    if "." in path:
        keys = path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value
    return data.get(path)


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


def transform_output(
    response: Dict[str, Any],
    output_schema: Optional[Dict[str, Any]],
    job_id: str,
    session_id: Optional[str] = None,
    agent_used: Optional[str] = None
) -> Dict[str, Any]:
    """
    Transform worker response based on output_schema mappings.
    
    Returns transformed dict ready for webhook delivery.
    """
    mappings = output_schema.get("mappings", {}) if output_schema else {}
    defaults = output_schema.get("defaults", {}) if output_schema else {}
    message_required = output_schema.get("messageRequired", True) if output_schema else True
    session_id_field = output_schema.get("sessionIdField", "session_id") if output_schema else "session_id"
    
    transformed = {
        "job_id": job_id,
    }
    
    if session_id:
        set_nested_value(transformed, session_id_field, session_id)
        
    if agent_used:
        transformed["agent_used"] = agent_used
    
    for internal_field, external_field in mappings.items():
        value = get_nested_value(response, internal_field)
        if value is not None:
            set_nested_value(transformed, external_field, value)
            
    if "result" not in transformed and "message" not in transformed:
        message_value = get_nested_value(response, "result") or get_nested_value(response, "message")
        if message_value is not None:
            transformed["result"] = message_value
        elif message_required:
            raise ValueError("message (result) is required but not found in worker response")
        else:
            transformed["result"] = ""
    
    for key, default_value in defaults.items():
        if key not in transformed:
            transformed[key] = default_value
    
    if "response" not in transformed:
        transformed["response"] = response
    
    if "timestamp" not in transformed:
        from datetime import datetime, timezone
        transformed["timestamp"] = datetime.now(timezone.utc).isoformat()
    
    return transformed