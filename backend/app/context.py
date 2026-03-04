from contextvars import ContextVar
from typing import Dict, Any, Optional

# Context variable to store request-scoped data (like context_data from webhook)
request_context_var: ContextVar[Optional[Dict[str, Any]]] = ContextVar("request_context", default=None)

def set_request_context(data: Dict[str, Any]):
    """Set the current request context data"""
    request_context_var.set(data)

def get_request_context() -> Dict[str, Any]:
    """Get the current request context data"""
    return request_context_var.get() or {}
