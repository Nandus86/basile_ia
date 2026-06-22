import requests
import json

share_token = "2ad4f39a-3a52-4243-8076-59ca307041f0"

def main():
    # 1. Try to fetch the run
    url_run = f"https://api.smith.langchain.com/api/v1/public/{share_token}/run"
    print(f"Fetching main run from {url_run}...")
    r = requests.get(url_run)
    print("Status:", r.status_code)
    run_id = None
    if r.status_code == 200:
        data = r.json()
        run_id = data.get("id")
        print(f"Main Run ID: {run_id}")
        with open("langsmith_run.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    else:
        print("Response:", r.text[:200])

    # 2. Try to query the runs (child runs)
    # The public query API gets runs shared under this token
    url_query = f"https://api.smith.langchain.com/api/v1/public/{share_token}/runs"
    print(f"Querying child runs from {url_query}...")
    
    # Let's try GET first
    r_query = requests.get(url_query)
    print("GET runs status:", r_query.status_code)
    if r_query.status_code == 200:
        q_data = r_query.json()
        with open("langsmith_query.json", "w", encoding="utf-8") as f:
            json.dump(q_data, f, indent=2, ensure_ascii=False)
        print(f"Successfully saved {len(q_data.get('runs', [])) if isinstance(q_data, dict) else len(q_data)} runs to langsmith_query.json")
        return
        
    # If GET fails, let's try POSTing to runs/query
    url_query_post = f"https://api.smith.langchain.com/api/v1/public/{share_token}/runs/query"
    print(f"Querying child runs POST from {url_query_post}...")
    r_query_post = requests.post(url_query_post, json={})
    print("POST runs status:", r_query_post.status_code)
    if r_query_post.status_code == 200:
        q_data = r_query_post.json()
        with open("langsmith_query.json", "w", encoding="utf-8") as f:
            json.dump(q_data, f, indent=2, ensure_ascii=False)
        print(f"Successfully saved POST runs to langsmith_query.json")
    else:
        print("Response:", r_query_post.text[:200])

if __name__ == "__main__":
    main()
