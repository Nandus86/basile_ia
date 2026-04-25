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
    
    transformed = {
        "job_id": job_id,
    }
    
    if session_id:
        transformed["session_id"] = session_id
    if agent_used:
        transformed["agent_used"] = agent_used
    
    for internal_field, external_field in mappings.items():
        value = get_nested_value(response, internal_field)
        if value is not None:
            set_nested_value(transformed, external_field, value)
    
    for key, default_value in defaults.items():
        if key not in transformed:
            transformed[key] = default_value
    
    if "response" not in transformed:
        transformed["response"] = response
    
    if "timestamp" not in transformed:
        from datetime import datetime, timezone
        transformed["timestamp"] = datetime.now(timezone.utc).isoformat()
    
    return transformed