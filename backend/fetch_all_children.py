import requests
import json
import os
import sys

# Ensure stdout handles UTF-8 (especially on Windows)
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

share_token = "2ad4f39a-3a52-4243-8076-59ca307041f0"

def fetch_run(run_id):
    url = f"https://api.smith.langchain.com/api/v1/public/{share_token}/run/{run_id}"
    r = requests.get(url)
    if r.status_code == 200:
        return r.json()
    else:
        print(f"Error fetching run {run_id}: {r.status_code}")
        return None

def main():
    # Load root run
    with open("langsmith_run.json", "r", encoding="utf-8") as f:
        root_run = json.load(f)

    all_runs = {}
    all_runs[root_run["id"]] = root_run

    # Queue of run IDs to fetch
    to_fetch = list(root_run.get("child_run_ids") or [])
    print(f"Root child run count to fetch: {len(to_fetch)}")

    fetched_count = 0
    while to_fetch:
        curr_id = to_fetch.pop(0)
        if curr_id in all_runs:
            continue
        
        print(f"Fetching child run {curr_id}...")
        run_data = fetch_run(curr_id)
        if run_data:
            all_runs[curr_id] = run_data
            fetched_count += 1
            # Add any children of this run to the queue (if any are not loaded)
            child_ids = run_data.get("child_run_ids") or []
            for cid in child_ids:
                if cid not in all_runs and cid not in to_fetch:
                    to_fetch.append(cid)

    print(f"Fetched {fetched_count} child runs. Total runs in trace: {len(all_runs)}")

    # Save all fetched runs to a single file
    with open("all_trace_runs.json", "w", encoding="utf-8") as f:
        json.dump(list(all_runs.values()), f, indent=2, ensure_ascii=False)
    print("Saved all runs to all_trace_runs.json")

    # Generate tree analysis in UTF-8 file
    # We will build the parent-child mapping
    children = {}
    for r_id, r in all_runs.items():
        parent_id = r.get("parent_run_id")
        if parent_id:
            if parent_id not in children:
                children[parent_id] = []
            children[parent_id].append(r)

    # Sort children by start_time
    for p_id in children:
        children[p_id].sort(key=lambda x: x.get("start_time") or "")

    report_lines = []

    def format_run(run, depth=0):
        indent = "  " * depth
        name = run.get("name")
        run_type = run.get("run_type")
        status = run.get("status")
        
        # Duration
        from datetime import datetime
        st_str = run.get("start_time")
        et_str = run.get("end_time")
        dur = "unknown"
        if st_str and et_str:
            try:
                st = datetime.fromisoformat(st_str.replace("Z", "+00:00"))
                et = datetime.fromisoformat(et_str.replace("Z", "+00:00"))
                dur = f"{(et - st).total_seconds():.3f}s"
            except Exception:
                pass

        report_lines.append(f"{indent}- [{run_type.upper()}] {name} | Status: {status} | Duration: {dur} | ID: {run['id']}")
        
        inputs = run.get("inputs") or {}
        outputs = run.get("outputs") or {}
        error = run.get("error")

        if run_type == "llm":
            messages = inputs.get("messages") or []
            if messages:
                report_lines.append(f"{indent}    Messages Count: {len(messages)}")
                # Show last user message
                last_user = None
                for m in reversed(messages):
                    m_role = m.get("role") or m.get("type")
                    if m_role in ("user", "human"):
                        last_user = m.get("content") or m.get("text")
                        break
                if last_user:
                    report_lines.append(f"{indent}    Last User Input: {str(last_user)[:300]}")
            else:
                prompt = inputs.get("prompt") or inputs.get("prompts")
                if prompt:
                    report_lines.append(f"{indent}    Prompt: {str(prompt)[:300]}")

            # Show output
            generations = outputs.get("generations") or []
            if generations:
                for gen in generations:
                    if isinstance(gen, list):
                        for g in gen:
                            text = g.get("text") or g.get("message", {}).get("content")
                            report_lines.append(f"{indent}    Output Gen: {str(text)[:400]}")
                    elif isinstance(gen, dict):
                        text = gen.get("text") or gen.get("message", {}).get("content")
                        report_lines.append(f"{indent}    Output Gen: {str(text)[:400]}")
            else:
                report_lines.append(f"{indent}    Output: {str(outputs)[:400]}")
            
            if error:
                report_lines.append(f"{indent}    Error: {error}")

        elif run_type == "tool":
            report_lines.append(f"{indent}    Input: {str(inputs)}")
            report_lines.append(f"{indent}    Output: {str(outputs)}")
            if error:
                report_lines.append(f"{indent}    Error: {error}")

        # Recurse
        for child in children.get(run["id"], []):
            format_run(child, depth + 1)

    format_run(root_run)

    with open("trace_tree_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print("Saved trace tree report to trace_tree_report.txt")

if __name__ == "__main__":
    main()
