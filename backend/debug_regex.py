import re
import json

text = '{"church_id": "{{ $request.church._id }}"}'
print('Input text:', repr(text))

pattern = r'\{\{\s*(?:\$request\.(.+?)|JSONStringify\(\$request\.(.+?)\))\s*\}\}'
matches = list(re.finditer(pattern, text))
print(f'Found {len(matches)} matches')
for m in matches:
    print(f'  Full match: {m.group(0)!r}')
    print(f'  Group 1: {m.group(1)!r}')
    print(f'  Group 2: {m.group(2)!r}')

# Simulate what happens in production
context = {
    "church": {
        "_id": "68ff5a3c4177621d0b00faa9",
        "role": "church"
    },
    "member": {"_id": "test123"},
    "session_id": "abc"
}

def _get_value_by_path(data, path):
    if not data or not path:
        return None
    parts = path.split('.')
    current = data
    for part in parts:
        if isinstance(current, str):
            try:
                current = json.loads(current)
            except:
                pass
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            current = current[idx] if idx < len(current) else None
        else:
            return None
    return current

# Test path resolution
path = "church._id"
val = _get_value_by_path(context, path)
print(f'\n_get_value_by_path(context, {path!r}) = {val!r}')

# Test full inject
def _inject_request_params(text, context_data):
    if not text or not context_data:
        return text
    def replacer(match):
        path = match.group(1) or match.group(2)
        if not path:
            return match.group(0)
        path = path.strip()
        val = _get_value_by_path(context_data, path)
        if val is None and isinstance(context_data.get("request"), dict):
            val = _get_value_by_path(context_data["request"], path)
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

result = _inject_request_params(text, context)
print(f'\nResult: {result}')

# Now test with context that has NO church (simulating filtered context)
filtered_context = {
    "member": {"_id": "test123"},
    "system": {"name": "test"},
    "ai_params": {"name": "Eva"},
    "session_id": "abc"
}
result2 = _inject_request_params(text, filtered_context)
print(f'\nResult with filtered (no church): {result2}')
