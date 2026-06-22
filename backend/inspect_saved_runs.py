import json

with open("all_trace_runs.json", "r", encoding="utf-8") as f:
    runs = json.load(f)

for r in runs:
    inputs = r.get("inputs") or {}
    messages = inputs.get("messages") or []
    if messages:
        print(f"Run {r.get('name')} | messages type: {type(messages)}")
        if len(messages) > 0:
            first_m = messages[0]
            print(f"  first message type: {type(first_m)}")
            print(f"  first message value: {str(first_m)[:200]}")
