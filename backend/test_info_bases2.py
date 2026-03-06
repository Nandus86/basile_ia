import httpx
import uuid
import sys

URL = "http://localhost:8080" # internal docker port

def run_tests():
    print("Starting HTTP tests...")
    
    with httpx.Client() as client:
        # 1. Create Info Base
        db_code = f"test_base_{uuid.uuid4().hex[:8]}"
        print(f"Creating info base with code {db_code}...")
        res = client.post(f"{URL}/information-bases", json={
            "name": "Integration Test Base",
            "code": db_code,
            "content_schema": {"type": "object", "properties": {"info": {"type": "string"}}},
            "metadata_schema": {"type": "object", "properties": {"source": {"type": "string"}}},
            "is_active": True
        })
        
        if res.status_code != 201:
            print("Failed to create info base:", res.text)
            sys.exit(1)
        base_id = res.json()["id"]
        print(f"Created info base ID: {base_id}")
        
        # 2. Ingest via Webhook
        user_id = str(uuid.uuid4())
        print(f"Ingesting webhook data for user {user_id}...")
        res = client.post(f"{URL}/information-bases/webhook", json={
            "id_base": db_code,
            "id": user_id,
            "data": {
                "info": "This is a secret integration test info.",
                "source": "automated_test"
            }
        })
        
        if res.status_code != 200:
            print("Failed to ingest webhook:", res.text)
            sys.exit(1)
        print("Webhook response:", res.json())
        sys.exit(0)

if __name__ == "__main__":
    run_tests()
