import urllib.parse
import re
import ast

def _inject_from_ai_params(text: str, kwargs: dict) -> str:
    if not text:
        return text
    
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
                if isinstance(val, bool):
                     return 'true' if val else 'false'
                return str(val)
            elif default is not None:
                if isinstance(default, bool):
                     return 'true' if default else 'false'
                return str(default)
            return match.group(0)
        except:
            return match.group(0)
            
    return re.sub(r'\{\{\s*\$fromAI\((.*?)\)\s*\}\}', replacer, text)


# Scenario 1 - Normal Text
scenario1 = "{{ $fromAI('body-base_url_basileia','Base Url do Servidor - Está em Global ou Contexto','string','https://dash.basileia.global') }}/api/solicitation/types/n8n/{{ $fromAI('member-phone','Número de telefone do membro - Está em Contexto','string') }}"

# Scenario 2 - URL Encoded text
scenario2 = "%7B%7B%20%24fromAI%28%27body-base_url_basileia%27%2C%27Base%20Url%20do%20Servidor%20-%20Est%C3%A1%20em%20Global%20ou%20Contexto%27%2C%27string%27%2C%27https%3A%2F%2Fdash.basileia.global%27%29%20%7D%7D%2Fapi%2Fsolicitation%2Ftypes%2Fn8n%2F%7B%7B%20%24fromAI%28%27member-phone%27%2C%27N%C3%BAmero%20de%20telefone%20do%20membro%20-%20Est%C3%A1%20em%20Contexto%27%2C%27string%27%29%20%7D%7D"

final_args = {
    'body-base_url_basileia': 'https://dash.basileia.global',
    'member-phone': '554399870910'
}

print("=== SCENARIO 1 ===")
print(_inject_from_ai_params(urllib.parse.unquote(scenario1), final_args))

print("\n=== SCENARIO 2 ===")
print(_inject_from_ai_params(urllib.parse.unquote(scenario2), final_args))

print("\n=== SCENARIO 3 ===")
endpoint_str = urllib.parse.unquote(scenario2)
# Here we check if httpx params argument correctly injects args
query = final_args
print("httpx query args passed:", query)
