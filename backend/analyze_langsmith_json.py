import json
from datetime import datetime

def parse_time(t_str):
    if not t_str:
        return None
    # Langsmith timestamps are often ISO with Z or offset
    # Let's parse ISO format.
    try:
        t_str = t_str.replace("Z", "+00:00")
        return datetime.fromisoformat(t_str)
    except Exception:
        return None

def main():
    try:
        with open("langsmith_run.json", "r", encoding="utf-8") as f:
            root_run = json.load(f)
    except Exception as e:
        print("Failed to read root run:", e)
        return

    try:
        with open("langsmith_query.json", "r", encoding="utf-8") as f:
            query_data = json.load(f)
    except Exception as e:
        print("Failed to read query data:", e)
        return

    runs = query_data if isinstance(query_data, list) else query_data.get("runs", [])
    print(f"Total runs fetched: {len(runs)}")

    # Index runs by ID
    run_dict = {}
    for r in runs:
        r_id = r.get("id")
        run_dict[r_id] = r
    
    # Also add root run if not present
    root_id = root_run.get("id")
    if root_id not in run_dict:
        run_dict[root_id] = root_run

    # Build parent-child tree
    children = {}
    for r_id, r in run_dict.items():
        parent_id = r.get("parent_run_id")
        if parent_id:
            if parent_id not in children:
                children[parent_id] = []
            children[parent_id].append(r)

    # Sort children by start_time
    for p_id in children:
        children[p_id].sort(key=lambda x: x.get("start_time") or "")

    # Print Tree Function
    def print_tree(run_id, depth=0):
        run = run_dict.get(run_id)
        if not run:
            return
        
        name = run.get("name")
        run_type = run.get("run_type")
        start_time = run.get("start_time")
        end_time = run.get("end_time")
        status = run.get("status")
        
        # Calculate duration
        dur = ""
        st = parse_time(start_time)
        et = parse_time(end_time)
        if st and et:
            dur = f"{(et - st).total_seconds():.3f}s"

        inputs = run.get("inputs")
        outputs = run.get("outputs")
        error = run.get("error")

        indent = "  " * depth
        print(f"{indent}- [{run_type.upper()}] {name} | Status: {status} | Duration: {dur} | ID: {run_id}")

        # If it is an LLM, print a short snippet of inputs and outputs
        if run_type == "llm":
            # Extract prompt messages
            messages = inputs.get("messages") or []
            if messages:
                print(f"{indent}    Input Msg Count: {len(messages)}")
                # Print last user message if any
                for m in reversed(messages):
                    # messages can be dict or list of dicts
                    if isinstance(m, dict):
                        m_content = m.get("content") or m.get("text")
                        m_role = m.get("role") or m.get("type")
                        if m_role == "user" or m_role == "human":
                            print(f"{indent}    Last User Msg: {str(m_content)[:100]}...")
                            break
            else:
                prompt = inputs.get("prompt") or inputs.get("prompts")
                if prompt:
                    print(f"{indent}    Prompt: {str(prompt)[:120]}...")
            
            # Print output content
            if outputs:
                generations = outputs.get("generations") or []
                if generations:
                    for gen in generations:
                        if isinstance(gen, list):
                            for g in gen:
                                text = g.get("text") or g.get("message", {}).get("content")
                                print(f"{indent}    Gen Output: {str(text)[:200]}...")
                        elif isinstance(gen, dict):
                            text = gen.get("text") or gen.get("message", {}).get("content")
                            print(f"{indent}    Gen Output: {str(text)[:200]}...")
                else:
                    print(f"{indent}    Outputs: {str(outputs)[:200]}...")
            if error:
                print(f"{indent}    Error: {error}")

        # If it's a tool, print input/output
        elif run_type == "tool":
            print(f"{indent}    Tool Input: {str(inputs)[:120]}...")
            print(f"{indent}    Tool Output: {str(outputs)[:120]}...")
            if error:
                print(f"{indent}    Error: {error}")

        # Recursively print children
        for child in children.get(run_id, []):
            print_tree(child.get("id"), depth + 1)

    print("\n--- EXECUTION TREE ---")
    print_tree(root_id)
    print("----------------------\n")

if __name__ == "__main__":
    main()
