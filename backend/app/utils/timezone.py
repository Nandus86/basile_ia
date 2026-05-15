from typing import Optional, Dict, Any
from zoneinfo import ZoneInfo

def resolve_timezone_name(payload: Dict[str, Any], path: Optional[str] = None) -> str:
    """
    Resolves a timezone name from a payload using a dot-notation path.
    Defaults to America/Sao_Paulo if not found or invalid.
    
    Args:
        payload: The data structure to search in.
        path: Dot-notation path (e.g. "church.address.timezone"). 
              If None, it tries a set of default paths.
    """
    default_tz = "America/Sao_Paulo"
    
    # If no path provided, try common default locations
    if not path:
        # Default 1: church.address.timezone
        # Default 2: zoneName
        tz = _get_nested(payload, "church.address.timezone") or payload.get("zoneName")
        if isinstance(tz, str) and tz:
            try:
                ZoneInfo(tz)
                return tz
            except Exception:
                pass
        return default_tz

    # Custom path resolution
    # Clean template markers if present
    clean_path = path.replace("{{", "").replace("}}", "").replace("$timestamp.", "").strip()
    
    resolved = _get_nested(payload, clean_path)
    
    if isinstance(resolved, str) and resolved:
        try:
            ZoneInfo(resolved)
            return resolved
        except Exception:
            pass
            
    return default_tz

def _get_nested(data: Dict[str, Any], path: str) -> Any:
    """Helper to get nested dictionary values using dot notation."""
    if not data or not path:
        return None
    
    parts = path.split(".")
    curr = data
    for p in parts:
        if isinstance(curr, dict) and p in curr:
            curr = curr[p]
        else:
            return None
    return curr
