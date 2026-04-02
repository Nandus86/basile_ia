"""
Semantic Ingestion Service
Transforms structured webhook data into semantically-chunked vectors for optimal retrieval.

Key concepts:
  - "semantic: true" fields → included in summary phrase (search index)
  - "vectorize: true" fields → get their own dedicated vectors (field-level chunks)
  - All original data is ALWAYS preserved in metadata (returned to agent)
"""
import json
import logging
import re
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Maximum number of vectors per record (1 summary + up to 9 field chunks)
MAX_FACETS_PER_RECORD = 10


def _has_semantic_flags(content_schema: Optional[Dict[str, Any]]) -> bool:
    """Check if a content_schema has any semantic or vectorize flags."""
    if not content_schema or not isinstance(content_schema, dict):
        return False
    props = content_schema.get("properties", {})
    if not isinstance(props, dict):
        return False
    return any(
        isinstance(v, dict) and (v.get("semantic") or v.get("vectorize"))
        for v in props.values()
    )


def _get_schema_fields(content_schema: Dict[str, Any]) -> Tuple[List[str], List[str], List[str]]:
    """Parse content_schema and return (semantic_fields, vectorize_fields, all_declared_fields).
    
    Returns:
        semantic_fields: fields with "semantic": true
        vectorize_fields: fields with "vectorize": true
        all_declared_fields: all fields declared in schema
    """
    props = content_schema.get("properties", {})
    if not isinstance(props, dict):
        return [], [], []
    
    semantic = []
    vectorize = []
    all_fields = list(props.keys())
    
    for field_name, field_def in props.items():
        if not isinstance(field_def, dict):
            continue
        if field_def.get("semantic"):
            semantic.append(field_name)
        if field_def.get("vectorize"):
            vectorize.append(field_name)
    
    return semantic, vectorize, all_fields


def _format_value(value: Any) -> str:
    """Format a value for natural text representation."""
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def build_summary_text(data: Dict[str, Any], semantic_fields: List[str]) -> str:
    """Build a natural-text summary from semantic fields for vector search.
    
    Creates a prose-like sentence from the structured data, which embeds
    much better than raw JSON for semantic search.
    """
    parts = []
    
    # Collect name-like fields first for subject context
    name_val = None
    for key in ["name", "nome", "title", "titulo", "label"]:
        if key in data and data[key]:
            name_val = str(data[key])
            break
    
    for field in semantic_fields:
        val = data.get(field)
        if val is None or val == "" or val == []:
            continue
        
        formatted = _format_value(val)
        if not formatted:
            continue
        
        # Build contextual phrase based on field semantics
        field_lower = field.lower()
        
        # Skip name field — we'll use it as subject prefix
        if field_lower in ("name", "nome", "title", "titulo", "label") and name_val:
            parts.insert(0, formatted)
            continue
        
        # Location-like fields
        if any(k in field_lower for k in ("address", "endereco", "local", "location", "cidade", "bairro")):
            if name_val:
                parts.append(f"localizado em {formatted}")
            else:
                parts.append(f"Local: {formatted}")
            continue
        
        # Role/function fields
        if any(k in field_lower for k in ("role", "cargo", "funcao", "função")):
            parts.append(f"função: {formatted}")
            continue
        
        # Date/time fields
        if any(k in field_lower for k in ("data", "date", "horario", "hora", "time", "inicio", "fim")):
            parts.append(f"{field}: {formatted}")
            continue
        
        # Category/type fields
        if any(k in field_lower for k in ("categoria", "category", "tipo", "type", "grupo", "group")):
            parts.append(f"categoria: {formatted}")
            continue
        
        # Description/notes — include content directly
        if any(k in field_lower for k in ("descricao", "description", "notes", "notas", "obs", "observacao", "detalhes", "resumo", "bio")):
            parts.append(formatted)
            continue
        
        # Arrays
        if isinstance(val, list):
            parts.append(f"{field}: {formatted}")
            continue
        
        # Default: field: value
        parts.append(f"{field}: {formatted}")
    
    return ". ".join(parts) if parts else ""


def _semantic_chunk_long_text(text: str) -> List[str]:
    """Use SemanticChunker for long text fields (>2000 chars).
    Falls back to simple sentence splitting if SemanticChunker fails.
    """
    if len(text) <= 2000:
        return [text]
    
    try:
        from langchain_experimental.text_splitter import SemanticChunker
        from langchain_openai import OpenAIEmbeddings
        
        chunker = SemanticChunker(
            OpenAIEmbeddings(model="text-embedding-3-small"),
            breakpoint_threshold_type="percentile",
            breakpoint_threshold_amount=85,
        )
        docs = chunker.create_documents([text])
        chunks = [doc.page_content for doc in docs if doc.page_content.strip()]
        
        if chunks:
            logger.info(f"[SemanticIngestion] SemanticChunker produced {len(chunks)} chunks from {len(text)} chars")
            return chunks
    except Exception as e:
        logger.warning(f"[SemanticIngestion] SemanticChunker failed, using sentence fallback: {e}")
    
    # Fallback: split by sentences, group into ~1500 char chunks
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ""
    for sent in sentences:
        if len(current) + len(sent) > 1500 and current:
            chunks.append(current.strip())
            current = sent
        else:
            current = f"{current} {sent}" if current else sent
    if current.strip():
        chunks.append(current.strip())
    
    return chunks if chunks else [text]


def process_webhook_payload(
    data: Dict[str, Any],
    content_schema: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Process webhook data into semantic facets for vectorization.
    
    Returns a list of facets, each containing:
      - "content": text to be vectorized (search index)
      - "facet_type": "summary" | "field:<name>" | "field:<name>:chunk:<i>"
      - "metadata": original complete data (always the full payload)
    
    If content_schema has no semantic flags, returns a single facet
    with the raw JSON dump (backward compatibility).
    """
    
    # === Backward compat: no schema or no semantic flags ===
    if not _has_semantic_flags(content_schema):
        return [{
            "content": json.dumps(data, ensure_ascii=False, indent=2),
            "facet_type": "raw",
            "metadata": data,
        }]
    
    semantic_fields, vectorize_fields, all_fields = _get_schema_fields(content_schema)
    
    facets = []
    metadata_json = data  # Always the full original payload
    
    # === Facet 1: Summary (from semantic fields) ===
    if semantic_fields:
        summary = build_summary_text(data, semantic_fields)
        if summary:
            facets.append({
                "content": summary,
                "facet_type": "summary",
                "metadata": metadata_json,
            })
    
    # === Facets 2+: Dedicated vectors for vectorize fields ===
    for field_name in vectorize_fields:
        val = data.get(field_name)
        if val is None or val == "" or val == []:
            continue
        
        text = _format_value(val)
        if not text.strip():
            continue
        
        # If text is long, use semantic chunking
        chunks = _semantic_chunk_long_text(text)
        
        for i, chunk in enumerate(chunks):
            facet_type = f"field:{field_name}" if len(chunks) == 1 else f"field:{field_name}:chunk:{i}"
            facets.append({
                "content": chunk,
                "facet_type": facet_type,
                "metadata": metadata_json,
            })
            
            # Respect MAX_FACETS limit
            if len(facets) >= MAX_FACETS_PER_RECORD:
                logger.warning(f"[SemanticIngestion] Hit max facets limit ({MAX_FACETS_PER_RECORD})")
                return facets
    
    # If no facets were generated (e.g., all fields empty), fallback to raw
    if not facets:
        return [{
            "content": json.dumps(data, ensure_ascii=False, indent=2),
            "facet_type": "raw",
            "metadata": metadata_json,
        }]
    
    logger.info(f"[SemanticIngestion] Generated {len(facets)} facets (1 summary + {len(facets)-1} field chunks)")
    return facets
