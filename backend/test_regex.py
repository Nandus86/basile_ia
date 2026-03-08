import urllib.parse
import re

text = "https://dash.basileia.global/api/solicitation/types/n8n/%7B%7B%20$fromAI('member-phone','N%C3%BAmero%20de%20telefone%20do%20membro%20-%20Est%C3%A1%20em%20Contexto','string')%20%7D%7D?church_id=68ff5a3c4177621d0b00faa9&church-_id=68ff5a3c4177621d0b00faa9"

decoded_text = urllib.parse.unquote(text)
print("Decoded URL:", decoded_text)

print("\n--- TEST EXTRACT ---")
matches = re.finditer(r'\{\{\s*\$fromAI\((.*?)\)\s*\}\}', decoded_text)
for m in matches:
    print("Found:", m.group(1))

print("\n--- TEST INJECT ---")
kwargs = {"member-phone": "554399870910"}

import ast
def replacer(match):
    args_str = match.group(1)
    try:
        args = ast.literal_eval(f'({args_str},)')
        if not args:
            return match.group(0)
        name = args[0]
        default = args[3] if len(args) > 3 else None
        
        val = kwargs.get(name)
        if val is not None:
             return str(val)
        elif default is not None:
             return str(default)
        return match.group(0)
    except Exception as e:
        print("Inject Eval error:", e)
        return match.group(0)

new_text = re.sub(r'\{\{\s*\$fromAI\((.*?)\)\s*\}\}', replacer, decoded_text)
print("Resulting URL:")
print(new_text)
