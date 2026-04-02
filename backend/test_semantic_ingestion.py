"""
Test cases for semantic_ingestion service.
Run: python test_semantic_ingestion.py
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(__file__))

from app.services.semantic_ingestion import (
    _has_semantic_flags,
    _get_schema_fields,
    build_summary_text,
    process_webhook_payload,
)


# ===== Test Data =====

SCHEMA_WITH_FLAGS = {
    "properties": {
        "nome": {"type": "string", "semantic": True},
        "categoria": {"type": "string", "semantic": True},
        "data": {"type": "string", "semantic": True},
        "local": {"type": "string", "semantic": True},
        "vagas": {"type": "number"},
        "inscritos": {"type": "number"},
        "descricao": {"type": "string", "semantic": True, "vectorize": True},
    }
}

SCHEMA_NO_FLAGS = {
    "properties": {
        "nome": {"type": "string"},
        "email": {"type": "string"},
    }
}

EVENT_DATA = {
    "nome": "Workshop de Louvor",
    "categoria": "música",
    "data": "2026-04-15",
    "local": "Salão Principal",
    "vagas": 30,
    "inscritos": 12,
    "descricao": "Neste workshop você vai aprender técnicas avançadas de louvor contemporâneo com o Pr. Carlos.",
}

MEMBER_DATA = {
    "_id": "member-456",
    "name": "João Silva",
    "phone": "11999887766",
    "role": "Líder de Louvor",
    "address": "Rua das Flores 123, São Paulo",
    "groups": ["Louvor", "Jovens"],
    "bank_details": {"agency": "001"},
}

MEMBER_SCHEMA = {
    "properties": {
        "name": {"type": "string", "semantic": True},
        "role": {"type": "string", "semantic": True},
        "address": {"type": "string", "semantic": True},
        "groups": {"type": "array", "semantic": True},
        "phone": {"type": "string"},
    }
}


# ===== Tests =====

def test_has_semantic_flags_true():
    assert _has_semantic_flags(SCHEMA_WITH_FLAGS) == True

def test_has_semantic_flags_false():
    assert _has_semantic_flags(SCHEMA_NO_FLAGS) == False

def test_has_semantic_flags_none():
    assert _has_semantic_flags(None) == False

def test_has_semantic_flags_empty():
    assert _has_semantic_flags({}) == False

def test_get_schema_fields():
    semantic, vectorize, all_fields = _get_schema_fields(SCHEMA_WITH_FLAGS)
    assert "nome" in semantic
    assert "categoria" in semantic
    assert "descricao" in semantic
    assert "descricao" in vectorize
    assert "vagas" not in semantic
    assert "vagas" not in vectorize
    assert "vagas" in all_fields

def test_build_summary_text_event():
    semantic_fields = ["nome", "categoria", "data", "local", "descricao"]
    summary = build_summary_text(EVENT_DATA, semantic_fields)
    assert "Workshop de Louvor" in summary
    assert "música" in summary
    # Description content should be present
    assert "louvor contemporâneo" in summary
    # Non-semantic fields should NOT appear
    assert "30" not in summary  # vagas
    assert "12" not in summary  # inscritos

def test_build_summary_text_member():
    semantic_fields = ["name", "role", "address", "groups"]
    summary = build_summary_text(MEMBER_DATA, semantic_fields)
    assert "João Silva" in summary
    assert "Líder de Louvor" in summary or "função" in summary
    assert "Rua das Flores" in summary
    assert "Louvor" in summary
    # Non-semantic fields
    assert "001" not in summary  # bank_details
    assert "member-456" not in summary  # _id

def test_process_webhook_no_schema():
    """No schema → fallback to raw JSON dump (backward compat)"""
    facets = process_webhook_payload(EVENT_DATA, None)
    assert len(facets) == 1
    assert facets[0]["facet_type"] == "raw"
    # Content should be JSON dump
    parsed = json.loads(facets[0]["content"])
    assert parsed["nome"] == "Workshop de Louvor"
    # Metadata should be original data
    assert facets[0]["metadata"] == EVENT_DATA

def test_process_webhook_schema_no_flags():
    """Schema without semantic/vectorize → fallback"""
    facets = process_webhook_payload(EVENT_DATA, SCHEMA_NO_FLAGS)
    assert len(facets) == 1
    assert facets[0]["facet_type"] == "raw"

def test_process_webhook_semantic_only():
    """Schema with semantic but no vectorize → just summary"""
    schema = {
        "properties": {
            "nome": {"type": "string", "semantic": True},
            "categoria": {"type": "string", "semantic": True},
        }
    }
    facets = process_webhook_payload(EVENT_DATA, schema)
    assert len(facets) == 1
    assert facets[0]["facet_type"] == "summary"
    assert "Workshop de Louvor" in facets[0]["content"]
    # Metadata should be complete original data
    assert facets[0]["metadata"]["vagas"] == 30

def test_process_webhook_with_vectorize():
    """Schema with semantic + vectorize → summary + field chunk"""
    facets = process_webhook_payload(EVENT_DATA, SCHEMA_WITH_FLAGS)
    
    # Should have at least 2: summary + descricao field
    assert len(facets) >= 2
    
    # First should be summary
    assert facets[0]["facet_type"] == "summary"
    assert "Workshop de Louvor" in facets[0]["content"]
    
    # Second should be the vectorized field
    field_facets = [f for f in facets if f["facet_type"].startswith("field:")]
    assert len(field_facets) >= 1
    assert "field:descricao" in field_facets[0]["facet_type"]
    assert "louvor contemporâneo" in field_facets[0]["content"]
    
    # ALL facets should have complete metadata
    for facet in facets:
        assert facet["metadata"]["vagas"] == 30
        assert facet["metadata"]["nome"] == "Workshop de Louvor"

def test_process_webhook_preserves_all_data():
    """Metadata must contain ALL original fields, even non-semantic ones"""
    facets = process_webhook_payload(MEMBER_DATA, MEMBER_SCHEMA)
    
    for facet in facets:
        meta = facet["metadata"]
        # ALL original fields must be in metadata
        assert meta["_id"] == "member-456"
        assert meta["phone"] == "11999887766"
        assert meta["bank_details"]["agency"] == "001"
        assert meta["name"] == "João Silva"

def test_process_webhook_empty_fields():
    """Fields with empty/None values should be skipped gracefully"""
    data = {"nome": "Test", "descricao": "", "vagas": None}
    schema = {
        "properties": {
            "nome": {"type": "string", "semantic": True},
            "descricao": {"type": "string", "semantic": True, "vectorize": True},
        }
    }
    facets = process_webhook_payload(data, schema)
    # Should only have summary (descricao is empty)
    assert len(facets) == 1
    assert facets[0]["facet_type"] == "summary"


# ===== Runner =====

if __name__ == "__main__":
    test_funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for fn in test_funcs:
        try:
            fn()
            print(f"  ✅ {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  💥 {fn.__name__}: {type(e).__name__}: {e}")
            failed += 1
    
    print(f"\n{'='*50}")
    print(f"  Results: {passed} passed, {failed} failed, {passed+failed} total")
    if failed:
        sys.exit(1)
    print("  All tests passed! ✅")
