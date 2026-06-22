import json
import os
import sys
from datetime import datetime

# Ensure stdout handles UTF-8
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def parse_time(t_str):
    if not t_str:
        return None
    try:
        return datetime.fromisoformat(t_str.replace("Z", "+00:00"))
    except Exception:
        return None

def extract_message_text(m):
    """Recursively extracts the role and content of a message from different LangChain formats."""
    if not m:
        return None, None
    
    if isinstance(m, list):
        # If it's a list, look at the first element or combine them
        if len(m) > 0:
            return extract_message_text(m[0])
        return None, None
        
    if isinstance(m, dict):
        # Check standard role and content
        role = m.get("role") or m.get("type")
        content = m.get("content") or m.get("text")
        
        # Check LangChain constructor format
        if m.get("type") == "constructor" and "kwargs" in m:
            kwargs = m.get("kwargs", {})
            content = kwargs.get("content") or kwargs.get("text")
            # The class name can indicate the role
            id_path = m.get("id") or []
            class_name = id_path[-1] if id_path else ""
            if "System" in class_name:
                role = "system"
            elif "Human" in class_name or "User" in class_name:
                role = "user"
            elif "AI" in class_name or "Assistant" in class_name:
                role = "assistant"
            elif "Function" in class_name or "Tool" in class_name:
                role = "tool"
        
        return role, content
        
    return None, str(m)

def main():
    if not os.path.exists("all_trace_runs.json"):
        print("all_trace_runs.json not found!")
        return
        
    with open("all_trace_runs.json", "r", encoding="utf-8") as f:
        runs = json.load(f)
        
    # Map runs by ID
    run_dict = {}
    for r in runs:
        run_dict[r["id"]] = r
        
    # Find root run (the run without a parent_run_id or with parent_run_id not in our list)
    root_run = None
    for r in runs:
        parent_id = r.get("parent_run_id")
        if not parent_id or parent_id not in run_dict:
            root_run = r
            break
            
    if not root_run:
        print("Could not identify root run.")
        if runs:
            root_run = runs[0]
        else:
            return

    # Build parent-child tree
    children = {}
    for r in runs:
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
        st_str = run.get("start_time")
        et_str = run.get("end_time")
        dur = "unknown"
        st = parse_time(st_str)
        et = parse_time(et_str)
        if st and et:
            dur = f"{(et - st).total_seconds():.3f}s"

        report_lines.append(f"{indent}- [{run_type.upper()}] {name} | Status: {status} | Duration: {dur} | ID: {run['id']}")
        
        inputs = run.get("inputs") or {}
        outputs = run.get("outputs") or {}
        error = run.get("error")

        # Extract messages
        messages = inputs.get("messages") or []
        # Sometimes messages is a nested list
        if isinstance(messages, list) and len(messages) > 0 and isinstance(messages[0], list):
            # Flatten one level
            flat_messages = []
            for item in messages:
                if isinstance(item, list):
                    flat_messages.extend(item)
                else:
                    flat_messages.append(item)
            messages = flat_messages

        if messages:
            report_lines.append(f"{indent}    Total Input Messages: {len(messages)}")
            
            # Find last user message
            last_user_msg = None
            for m in reversed(messages):
                role, content = extract_message_text(m)
                if role in ("user", "human", "HumanMessage"):
                    last_user_msg = content
                    break
            if last_user_msg:
                report_lines.append(f"{indent}    Last User Msg: {str(last_user_msg).strip()[:200]}...")

        if run_type == "llm":
            # Show outputs
            generations = outputs.get("generations") or []
            if generations:
                for gen in generations:
                    if isinstance(gen, list):
                        for g in gen:
                            text = g.get("text") or g.get("message", {}).get("content")
                            report_lines.append(f"{indent}    LLM Output Gen: {str(text).strip()[:300]}...")
                    elif isinstance(gen, dict):
                        text = gen.get("text") or gen.get("message", {}).get("content")
                        report_lines.append(f"{indent}    LLM Output Gen: {str(text).strip()[:300]}...")
            else:
                report_lines.append(f"{indent}    LLM Raw Output: {str(outputs).strip()[:300]}...")
                
        elif run_type == "tool":
            report_lines.append(f"{indent}    Tool Input: {str(inputs).strip()[:200]}...")
            report_lines.append(f"{indent}    Tool Output: {str(outputs).strip()[:300]}...")

        if error:
            report_lines.append(f"{indent}    Error: {error}")

        # Recurse
        for child in children.get(run["id"], []):
            format_run(child, depth + 1)

    format_run(root_run)

    report_content = "\n".join(report_lines)
    with open("trace_tree_report.txt", "w", encoding="utf-8") as f:
        f.write(report_content)
        
    print("Report generated successfully in trace_tree_report.txt!")

if __name__ == "__main__":
    main()
