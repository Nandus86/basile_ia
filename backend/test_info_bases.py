import uuid
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def run_tests():
    print("Starting tests...")
    
    # 1. Create Info Base
    db_code = f"test_base_{uuid.uuid4().hex[:8]}"
    print(f"Creating info base with code {db_code}...")
    res = client.post("/information-bases", json={
        "name": "Integration Test Base",
        "code": db_code,
        "content_schema": {"type": "object", "properties": {"info": {"type": "string"}}},
        "metadata_schema": {"type": "object", "properties": {"source": {"type": "string"}}},
        "is_active": True
    })
    
    if res.status_code != 201:
        print("Failed to create info base:", res.text)
        return
    base_id = res.json()["id"]
    print(f"Created info base ID: {base_id}")
    
    # 2. Ingest via Webhook
    user_id = str(uuid.uuid4())
    print(f"Ingesting webhook data for user {user_id}...")
    res = client.post("/information-bases/webhook", json={
        "id_base": db_code,
        "id": user_id,
        "data": {
            "info": "This is a secret integration test info.",
            "source": "automated_test"
        }
    })
    
    if res.status_code != 200:
        print("Failed to ingest webhook:", res.text)
        return
    print("Webhook response:", res.json())
    
    # 3. Create Agent
    print("Creating test agent...")
    res = client.post("/agents", json={
        "name": "Test Information Agent",
        "system_prompt": "You are a test agent.",
        "model": "gpt-4o-mini",
        "temperature": 0.0,
        "max_tokens": 100,
        "is_active": True,
        "access_level": "normal",
        "collaboration_enabled": False,
        "vector_memory_enabled": False
    })
    if res.status_code not in (200, 201):
        print("Failed to create agent:", res.text)
        return
    agent_id = res.json()["id"]
    print(f"Created agent ID: {agent_id}")
    
    # 4. Attach base to agent
    print("Attaching info base to agent...")
    res = client.post(f"/agents/{agent_id}/information-bases/{base_id}")
    if res.status_code not in (200, 201):
        print("Failed to attach base to agent:", res.text)
        return
    print("Attached base successfully. Agent bases:", res.json()["information_bases"])
    
    print("All tests passed successfully!")

if __name__ == "__main__":
    run_tests()
