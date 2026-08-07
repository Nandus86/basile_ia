import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from backend.app.services.mcp_tools import _inject_request_params

wf_context_data = {
    "_workflow_context": {
        "request": {
            "body": {
                "data": "test2"
            }
        }
    }
}

print("stringify:", _inject_request_params("{{ JSONStringify($request.body) }}", wf_context_data))
