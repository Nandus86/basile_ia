import json

with open("langsmith_run.json", "r", encoding="utf-8") as f:
    run = json.load(f)

print("KEYS in run:", list(run.keys()))
print("ID:", run.get("id"))
print("Name:", run.get("name"))
print("Session ID (if any):", run.get("session_id"))
print("Run Type:", run.get("run_type"))
print("Inputs:", run.get("inputs"))
print("Outputs:", run.get("outputs"))

with open("langsmith_query.json", "r", encoding="utf-8") as f:
    query = json.load(f)

print("\nKEYS in query:", list(query.keys()) if isinstance(query, dict) else "is a list")
if isinstance(query, dict):
    runs = query.get("runs", [])
    print("Number of runs in query:", len(runs))
    if runs:
        print("First run in query keys:", list(runs[0].keys()))
        print("First run name:", runs[0].get("name"))
        print("First run ID:", runs[0].get("id"))
        print("First run parent:", runs[0].get("parent_run_id"))
else:
    print("Query is list with length:", len(query))
    if query:
        print("First element keys:", list(query[0].keys()))
