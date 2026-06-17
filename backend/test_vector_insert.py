"""
Unit tests for the vector_insert block in WorkflowEngine.
Run: python test_vector_insert.py
"""
import sys
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(__file__))

# Mock weaviate_client before importing the engine or app parts
mock_weaviate_client = MagicMock()
mock_weaviate_client.delete_information_base_nodes = AsyncMock(return_value=None)
mock_weaviate_client.save_information_base_node = AsyncMock(return_value=True)

sys.modules['app.weaviate_client'] = MagicMock(weaviate_client=mock_weaviate_client)

from app.services.workflow_engine import WorkflowEngine
from app.models.information_base import InformationBase

# Sample schema and payload
TEST_SCHEMA = {
    "properties": {
        "title": {"type": "string", "semantic": True},
        "description": {"type": "string", "semantic": True, "vectorize": True},
        "category": {"type": "string"}
    }
}

TEST_PAYLOAD = {
    "title": "Nova Base de Conhecimento",
    "description": "Explicação detalhada sobre a funcionalidade do Weaviate no Basile.",
    "category": "tecnologia"
}

async def run_tests():
    print("Starting vector_insert block tests...")

    # 1. Mock Database AsyncSession
    mock_db = AsyncMock()
    
    # Mock information base record returned by DB
    mock_base = MagicMock(spec=InformationBase)
    mock_base.code = "test-base"
    mock_base.content_schema = TEST_SCHEMA
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=mock_base)
    mock_db.execute = AsyncMock(return_value=mock_result)

    # Initialize Engine
    engine = WorkflowEngine(db=mock_db)

    # Context variables
    context = {
        "$trigger": {
            "payload": {
                "base_code_var": "test-base",
                "user_id_var": "user-123",
                "external_id_var": "ext-999",
                "data_var": TEST_PAYLOAD
            }
        }
    }

    # Block configuration
    config = {
        "base_code": "{{ $trigger.payload.base_code_var }}",
        "user_id": "{{ $trigger.payload.user_id_var }}",
        "external_id": "{{ $trigger.payload.external_id_var }}",
        "data": "{{ $trigger.payload.data_var }}"
    }

    # Reset mock calls
    mock_weaviate_client.delete_information_base_nodes.reset_mock()
    mock_weaviate_client.save_information_base_node.reset_mock()

    print("Executing _exec_vector_insert...")
    result = await engine._exec_vector_insert(config, context)

    print("Verifying outputs and mock calls...")
    
    # Verify DB query was executed
    assert mock_db.execute.called, "Database query should have been executed."
    
    # Verify cleanup / deletion was called with correct arguments
    mock_weaviate_client.delete_information_base_nodes.assert_called_once_with(
        base_code="test-base",
        user_id="user-123",
        external_id="ext-999"
    )
    print("  ✅ delete_information_base_nodes called correctly")

    # Verify save_information_base_node was called
    # With semantic+vectorize, there should be:
    # 1. Summary facet
    # 2. Field facet (field:description)
    assert mock_weaviate_client.save_information_base_node.call_count >= 2, "Should save at least 2 facets."
    print("  ✅ save_information_base_node called for multiple facets")

    # Verify result structure
    assert result["success"] is True
    assert result["saved_facets"] >= 2
    assert result["base_code"] == "test-base"
    assert result["user_id"] == "user-123"
    assert result["external_id"] == "ext-999"
    print("  ✅ return dictionary is fully populated and correct")

    print("\n==================================================")
    print("All vector_insert block tests passed successfully! ✅")

if __name__ == "__main__":
    asyncio.run(run_tests())
