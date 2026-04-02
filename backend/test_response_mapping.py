"""
Test cases for _apply_response_mapping with grouped field extraction.
Run: python -m pytest test_response_mapping.py -v
"""
import json
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(__file__))

from app.services.mcp_tools import (
    _apply_response_mapping,
    _parse_group_fields,
    _truncate_large_response,
)


# ===== Test data =====
SAMPLE_API_RESPONSE = {
    "body": [
        {"_id": "abc123", "name": "João Silva", "phone": "11999887766", "email": "joao@test.com", "bank_details": {"agency": "001"}},
        {"_id": "def456", "name": "Maria Santos", "phone": "11888776655", "email": "maria@test.com", "bank_details": {"agency": "002"}},
        {"_id": "ghi789", "name": "Pedro Costa", "phone": "11777665544", "email": "pedro@test.com", "bank_details": {"agency": "003"}},
    ],
    "total": 3,
    "page": 1
}

NESTED_API_RESPONSE = {
    "data": {
        "results": [
            {"_id": "1", "profile": {"name": "Alice", "bio": "Uma bio muito longa que deveria ser truncada para caber no contexto do agente sem problema"}},
            {"_id": "2", "profile": {"name": "Bob", "bio": "Bio curta"}},
        ]
    }
}


# ===== Test _parse_group_fields =====

def test_parse_simple_fields():
    fields = _parse_group_fields("_id, name, phone")
    assert fields == [("_id", "_id"), ("name", "name"), ("phone", "phone")]


def test_parse_fields_with_alias():
    fields = _parse_group_fields("id: _id, nome: name, telefone: phone")
    assert fields == [("id", "_id"), ("nome", "name"), ("telefone", "phone")]


def test_parse_mixed_fields():
    fields = _parse_group_fields("_id, nome: name, phone")
    assert fields == [("_id", "_id"), ("nome", "name"), ("phone", "phone")]


def test_parse_nested_field_uses_last_segment():
    fields = _parse_group_fields("_id, profile.name, profile.bio")
    assert fields == [("_id", "_id"), ("name", "profile.name"), ("bio", "profile.bio")]


# ===== Test _apply_response_mapping - backward compat =====

def test_backward_compat_single_field():
    """Existing [*] syntax should still work"""
    mapping = {"ids": "body[*]._id"}
    result = _apply_response_mapping(SAMPLE_API_RESPONSE, mapping)
    assert result == {"ids": ["abc123", "def456", "ghi789"]}


def test_backward_compat_with_truncate():
    mapping = {"nomes": "body[*].name | truncate(5)"}
    result = _apply_response_mapping(SAMPLE_API_RESPONSE, mapping)
    # "João Silva" truncated to 5 chars -> "João " -> strip -> "João..."
    assert result["nomes"] == ["João...", "Maria...", "Pedro..."]


def test_backward_compat_scalar_field():
    mapping = {"total": "total", "page": "page"}
    result = _apply_response_mapping(SAMPLE_API_RESPONSE, mapping)
    assert result == {"total": 3, "page": 1}


# ===== Test _apply_response_mapping - grouped syntax =====

def test_grouped_simple():
    mapping = {"items": "body[*].{_id, name, phone}"}
    result = _apply_response_mapping(SAMPLE_API_RESPONSE, mapping)
    assert len(result["items"]) == 3
    assert result["items"][0] == {"_id": "abc123", "name": "João Silva", "phone": "11999887766"}
    assert result["items"][1] == {"_id": "def456", "name": "Maria Santos", "phone": "11888776655"}


def test_grouped_with_alias():
    mapping = {"membros": "body[*].{id: _id, nome: name, telefone: phone}"}
    result = _apply_response_mapping(SAMPLE_API_RESPONSE, mapping)
    assert len(result["membros"]) == 3
    assert result["membros"][0] == {"id": "abc123", "nome": "João Silva", "telefone": "11999887766"}


def test_grouped_excludes_unmentioned_fields():
    """Bank details and email should NOT appear since they're not in {fields}"""
    mapping = {"items": "body[*].{_id, name}"}
    result = _apply_response_mapping(SAMPLE_API_RESPONSE, mapping)
    for item in result["items"]:
        assert "bank_details" not in item
        assert "email" not in item
        assert "phone" not in item
        assert "_id" in item
        assert "name" in item


def test_grouped_nested_path():
    mapping = {"pessoas": "data.results[*].{_id, profile.name}"}
    result = _apply_response_mapping(NESTED_API_RESPONSE, mapping)
    assert len(result["pessoas"]) == 2
    # Nested field uses last segment as default alias
    assert result["pessoas"][0] == {"_id": "1", "name": "Alice"}
    assert result["pessoas"][1] == {"_id": "2", "name": "Bob"}


def test_grouped_nested_with_alias():
    mapping = {"pessoas": "data.results[*].{id: _id, nome: profile.name, descricao: profile.bio}"}
    result = _apply_response_mapping(NESTED_API_RESPONSE, mapping)
    assert result["pessoas"][0]["id"] == "1"
    assert result["pessoas"][0]["nome"] == "Alice"
    assert "Uma bio" in result["pessoas"][0]["descricao"]


def test_grouped_with_truncate():
    mapping = {"pessoas": "data.results[*].{_id, profile.bio} | truncate(20)"}
    result = _apply_response_mapping(NESTED_API_RESPONSE, mapping)
    # The long bio should be truncated
    assert len(result["pessoas"][0]["bio"]) <= 24  # 20 + "..."
    assert result["pessoas"][0]["bio"].endswith("...")
    # Short bio should not be truncated
    assert result["pessoas"][1]["bio"] == "Bio curta"


def test_grouped_mixed_with_scalar():
    """Can mix grouped and scalar mappings"""
    mapping = {
        "membros": "body[*].{_id, name}",
        "total": "total"
    }
    result = _apply_response_mapping(SAMPLE_API_RESPONSE, mapping)
    assert result["total"] == 3
    assert len(result["membros"]) == 3


# ===== Test _truncate_large_response fixes =====

def test_truncate_list_shows_correct_original_count():
    data = list(range(100))
    result = _truncate_large_response(data, max_len=10)
    assert result["total_items"] == 100
    assert "from 100 items to 3" in result["warning"]


def test_truncate_body_shows_correct_original_count():
    data = {"body": list(range(50))}
    result = _truncate_large_response(data, max_len=10)
    assert "from 50 to 3" in result["warning"]
    assert len(result["body"]) == 3


def test_truncate_small_data_unchanged():
    data = {"key": "value"}
    result = _truncate_large_response(data)
    assert result == data


# ===== Run tests =====

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
