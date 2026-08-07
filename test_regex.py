import re

text = '{"church_id": "{{ $request.church._id }}"}'
print("TEXT IS:", text)

pattern = r'\{\{[\s\+]*(?:\$request\.(.+?)|JSONStringify\(\$request\.(.+?)\))[\s\+]*\}\}'
matches = re.findall(pattern, text)
print("MATCHES:", matches)

# Try replacing
def replacer(match):
    print("Match groups:", match.groups())
    return "123"

print("REPLACED:", re.sub(pattern, replacer, text))
