import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from backend.app.services.mcp_tools import _get_value_by_path, _inject_request_params

context_data = {
    "request": {
        "headers": {
            "Authorization": "Bearer 123"
        },
        "body": {
            "data": "test"
        }
    }
}

text1 = "{{ $request.headers.Authorization }}"
text2 = "{{ $request.body.data }}"
text3 = "{{ $request.body }}"

print("text1:", _inject_request_params(text1, context_data))
print("text2:", _inject_request_params(text2, context_data))
print("text3:", _inject_request_params(text3, context_data))

# Also test workflow context
wf_context_data = {
    "_workflow_context": {
        "request": {
            "headers": {
                "Authorization": "Bearer 456"
            },
            "body": {
                "data": "test2"
            }
        }
    }
}

print("wf_text1:", _inject_request_params(text1, wf_context_data))
print("wf_text2:", _inject_request_params(text2, wf_context_data))
