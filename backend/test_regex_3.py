import json
import re

def _get_value_by_path(data: dict, path: str):
    if not data or not path:
        return None
    
    parts = path.split('.')
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            current = current[idx] if idx < len(current) else None
        else:
            return None
    return current

def _inject_request_params(text: str, context_data: dict) -> str:
    if not text or not context_data:
        return text
    
    def replacer(match):
        path = match.group(1) or match.group(2)
        if not path:
            return match.group(0)
        
        path = path.strip()
        val = _get_value_by_path(context_data, path)
        
        if val is None:
            return match.group(0)
            
        if isinstance(val, bool):
            res = "true" if val else "false"
        elif isinstance(val, (dict, list)):
            res = json.dumps(val, ensure_ascii=False)
        else:
            res = str(val)
        
        return res
            
    return re.sub(r'\{\{\s*(?:\$request\.(.+?)|JSONStringify\(\$request\.(.+?)\))\s*\}\}', replacer, text)


payload = {
  "message": "quais eventos tem na igreja?",
  "session_id": "68ff5a3c4177621d0b00faa85543999284670",
  "church": {
    "_id": "68ff5a3c4177621d0b00faa9",
    "role": "church",
    "phone": "5547992034898"
  },
  "global": {
    "phone": "5543999284670"
  }
}

query_template = {"church_id": "{{ $request.church._id }}"}
query_str = json.dumps(query_template)

print("Original query_str:", query_str)
resolved = _inject_request_params(query_str, payload)
print("Resolved query_str:", resolved)
print("Is val None?", _get_value_by_path(payload, "church._id"))

# Test with URL encoding
url_encoded_query_str = "%7B%7B+%24request.church._id+%7D%7D"
print("URL Encoded Original:", url_encoded_query_str)
resolved_encoded = _inject_request_params(url_encoded_query_str, payload)
print("Resolved URL Encoded:", resolved_encoded)

