"""
Structured Output Schemas and Dynamic Schema Builder
"""
from pydantic import BaseModel, Field, create_model
from typing import Optional, Literal, Dict, Any, Type, get_args
from enum import Enum


class AttendanceTag(str, Enum):
    """Default attendance tags for WhatsApp integration"""
    COLETANDO = "coletando"
    SOLUCAO = "solucao"
    RESOLVIDO = "resolvido"
    HUMANO = "humano"


class DefaultAgentOutput(BaseModel):
    """Default output schema - only response text"""
    output: str = Field(description="Resposta para o cliente")


class TaggedAgentOutput(BaseModel):
    """Output with attendance tag for WhatsApp triaging"""
    output: str = Field(description="Resposta para o cliente")
    tag: Literal["coletando", "solucao", "resolvido", "humano"] = Field(
        description="Estado atual do atendimento"
    )
    confidence: Optional[float] = Field(
        default=None, 
        ge=0, 
        le=1, 
        description="Confiança na resposta (0-1)"
    )
    next_action: Optional[str] = Field(
        default=None,
        description="Próxima ação sugerida"
    )


class StructuredProcessRequest(BaseModel):
    """Request for structured output processing"""
    message: str
    session_id: str
    agent_id: Optional[str] = None
    user_access_level: str = "normal"
    context_data: Optional[Dict[str, Any]] = None


class StructuredProcessResponse(BaseModel):
    """Response with structured output"""
    output: str = Field(description="Resposta do agente")
    agent_used: Optional[str] = None
    processing_time_ms: float = 0
    # Additional dynamic fields will be added based on agent's output_schema
    
    model_config = {"extra": "allow"}  # Allow dynamic fields


def build_schema_from_json(schema_dict: Dict[str, Any]) -> Type[BaseModel]:
    """
    Build a Pydantic model dynamically from a JSON schema definition.
    
    Example schema_dict:
    {
        "output": {"type": "string", "description": "Resposta para o cliente"},
        "tag": {"type": "string", "enum": ["coletando", "solucao", "resolvido", "humano"]},
        "urgency": {"type": "string", "enum": ["baixa", "media", "alta"]}
    }
    """
    if not schema_dict:
        return DefaultAgentOutput
    
    fields = {}
    
    for field_name, field_def in schema_dict.items():
        field_type = str  # default type
        field_default = ...  # required by default
        
        # Determine field type
        type_str = field_def.get("type", "string")
        
        if type_str == "number" or type_str == "float":
            field_type = float
        elif type_str == "integer" or type_str == "int":
            field_type = int
        elif type_str == "boolean" or type_str == "bool":
            field_type = bool
        elif type_str == "string":
            # Check for enum
            if "enum" in field_def:
                enum_values = tuple(field_def["enum"])
                field_type = Literal[enum_values]
            else:
                field_type = str
        
        # Check if optional
        if field_def.get("optional", False) or field_def.get("nullable", False):
            field_type = Optional[field_type]
            field_default = None
        
        # Build field with description
        description = field_def.get("description", "")
        
        if field_default is ...:
            fields[field_name] = (field_type, Field(description=description))
        else:
            fields[field_name] = (field_type, Field(default=field_default, description=description))
    
    # Create and return dynamic model
    return create_model("DynamicAgentOutput", **fields)


def get_output_schema_for_agent(output_schema: Optional[Dict[str, Any]]) -> Type[BaseModel]:
    """
    Get the appropriate output schema for an agent.
    Returns DefaultAgentOutput if no custom schema is defined.
    """
    if output_schema is None:
        return DefaultAgentOutput
    
    try:
        return build_schema_from_json(output_schema)
    except Exception as e:
        print(f"[StructuredOutput] Error building schema: {e}, using default")
        return DefaultAgentOutput


def filter_context_data(
    context_data: Optional[Dict[str, Any]],
    input_schema: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Filters context_data to only include keys present in the agent's input_schema.
    Ensures that each agent only sees its own domain data.
    Supports both whitelist ('properties') and blacklist/exclusion ('exclude' or 'omit').
    """
    if not context_data:
        return {}
    
    import json
    
    # Pre-process input_schema if it's a JSON string
    if isinstance(input_schema, str):
        try:
            input_schema = json.loads(input_schema)
        except Exception:
            input_schema = None
            
    # Extract properties and root exclude from standard JSON Schema formats (robust parsing)
    root_exclude = []
    if isinstance(input_schema, dict):
        raw_exclude = input_schema.get("exclude") or input_schema.get("omit") or []
        if isinstance(raw_exclude, str):
            root_exclude = [raw_exclude]
        elif isinstance(raw_exclude, list):
            root_exclude = raw_exclude

        if "properties" in input_schema:
            input_schema = input_schema["properties"]
        elif input_schema.get("type") == "object" and "properties" in input_schema:
            input_schema = input_schema["properties"]
        elif input_schema.get("type") == "object" and root_exclude:
            filtered_result = {k: v for k, v in context_data.items() if k not in set(root_exclude)}
            return filtered_result
            
    if not input_schema or not isinstance(input_schema, dict):
        # If no input_schema is defined, return the full context_data (pruning of request-only/sensitive fields still occurs inside AgentFactory)
        res = context_data.copy() if isinstance(context_data, dict) else {}
        if root_exclude and isinstance(res, dict):
            res = {k: v for k, v in res.items() if k not in set(root_exclude)}
        return res

    def filter_by_schema(data: Any, schema: Dict[str, Any]) -> Any:
        if not isinstance(data, dict):
            return data
        filtered = {}
        for key, field_def in schema.items():
            if key not in data:
                continue
            
            data_val = data[key]
            
            if isinstance(field_def, dict):
                field_type = field_def.get("type", "string")
                exclude_fields = field_def.get("exclude") or field_def.get("omit") or []
                if isinstance(exclude_fields, str):
                    exclude_fields = [exclude_fields]
                exclude_set = set(exclude_fields) if isinstance(exclude_fields, (list, set, tuple)) else set()

                if field_type == "object" and "properties" in field_def and isinstance(data_val, dict):
                    obj_res = filter_by_schema(data_val, field_def["properties"])
                    if exclude_set and isinstance(obj_res, dict):
                        filtered[key] = {k: v for k, v in obj_res.items() if k not in exclude_set}
                    else:
                        filtered[key] = obj_res
                elif field_type == "object" and isinstance(data_val, dict):
                    if exclude_set:
                        filtered[key] = {k: v for k, v in data_val.items() if k not in exclude_set}
                    else:
                        filtered[key] = data_val
                elif field_type == "array" and "items" in field_def and isinstance(field_def["items"], dict) and isinstance(data_val, list):
                    item_def = field_def["items"]
                    item_exclude = item_def.get("exclude") or item_def.get("omit") or []
                    if isinstance(item_exclude, str):
                        item_exclude = [item_exclude]
                    item_exclude_set = set(item_exclude) if isinstance(item_exclude, (list, set, tuple)) else set()

                    if "properties" in item_def:
                        filtered[key] = [
                            {k: v for k, v in filter_by_schema(item, item_def["properties"]).items() if k not in item_exclude_set}
                            if isinstance(item, dict) else item
                            for item in data_val
                        ]
                    elif item_exclude_set:
                        filtered[key] = [
                            {k: v for k, v in item.items() if k not in item_exclude_set}
                            if isinstance(item, dict) else item
                            for item in data_val
                        ]
                    else:
                        filtered[key] = data_val
                elif exclude_set and isinstance(data_val, dict):
                    filtered[key] = {k: v for k, v in data_val.items() if k not in exclude_set}
                else:
                    filtered[key] = data_val
            else:
                filtered[key] = data_val
        return filtered

    # Try standard filtering
    filtered_result = filter_by_schema(context_data, input_schema)
    if root_exclude and isinstance(filtered_result, dict):
        filtered_result = {k: v for k, v in filtered_result.items() if k not in set(root_exclude)}
    
    # Check if we have a nested "request" key in context_data (common in webhook tasks)
    # where the input_schema defines keys that exist inside context_data["request"] rather than at root
    if not filtered_result and "request" in context_data and isinstance(context_data["request"], dict):
        nested_filter = filter_by_schema(context_data["request"], input_schema)
        if nested_filter:
            if root_exclude and isinstance(nested_filter, dict):
                nested_filter = {k: v for k, v in nested_filter.items() if k not in set(root_exclude)}
            # Re-wrap in request key to preserve format expected by templates (e.g. $request.xxx)
            filtered_result = {"request": nested_filter}
            
    # Fallback: if filtering yields an empty result but original context_data exists,
    # return the full context_data copy to match pre-0.0.75 behavior and prevent blinding the agent.
    if not filtered_result and context_data:
        res = context_data.copy()
        if root_exclude and isinstance(res, dict):
            res = {k: v for k, v in res.items() if k not in set(root_exclude)}
        return res
        
    return filtered_result


def format_context_data_for_prompt(
    context_data: Optional[Dict[str, Any]],
    input_schema: Optional[Dict[str, Any]] = None
) -> str:
    """
    Format context_data cleanly using strict JSON.
    This preserves tags like {{ $fromAI(...) }} exactly as they came from the webhook
    so the agent can use them to call MCP tools.
    """
    import json
    
    filtered_data = filter_context_data(context_data, input_schema)
    
    if not filtered_data:
        return ""
        
    data_json = json.dumps(filtered_data, indent=2, ensure_ascii=False)
    
    # We display the schema parts in the prompt to help the agent understand what it has
    schema_parts = input_schema
    if isinstance(schema_parts, str):
        try:
            schema_parts = json.loads(schema_parts)
        except: pass
    if isinstance(schema_parts, dict) and "properties" in schema_parts:
        schema_parts = schema_parts["properties"]
        
    schema_section = ""
    if schema_parts:
        schema_json = json.dumps(schema_parts, indent=2, ensure_ascii=False)
        schema_section = f"O esquema esperado (Input Schema) é:\n{schema_json}\n\n"
        
    return f"""

## Dados de Contexto (Context Data)

{schema_section}Os seguintes dados foram fornecidos no contexto atual:
{data_json}

Use esses dados conforme necessário para ferramentas MCP e para basear suas respostas.
Não preencha tags {{{{ $fromAI }}}} no texto da resposta ao usuário, em vez disso, utilize-os para completar argumentos nas ferramentas que solicitar.
"""


# Pre-built schemas for common use cases (OUTPUT)
PRESET_SCHEMAS = {
    "default": {
        "output": {"type": "string", "description": "Resposta para o cliente"}
    },
    "whatsapp_triage": {
        "output": {"type": "string", "description": "Resposta para enviar no WhatsApp"},
        "tag": {
            "type": "string",
            "enum": ["coletando", "solucao", "resolvido", "humano"],
            "description": "Estado do atendimento"
        }
    },
    "sales_lead": {
        "output": {"type": "string", "description": "Resposta para o cliente"},
        "interest_level": {
            "type": "string",
            "enum": ["baixo", "medio", "alto"],
            "description": "Nível de interesse do lead"
        },
        "next_step": {
            "type": "string",
            "enum": ["agendar_demo", "enviar_proposta", "follow_up", "descartar"],
            "description": "Próximo passo sugerido"
        }
    },
    "support_ticket": {
        "output": {"type": "string", "description": "Resposta para o cliente"},
        "priority": {
            "type": "string",
            "enum": ["baixa", "media", "alta", "critica"],
            "description": "Prioridade do ticket"
        },
        "category": {
            "type": "string",
            "enum": ["tecnico", "financeiro", "comercial", "outro"],
            "description": "Categoria do problema"
        },
        "needs_human": {
            "type": "boolean",
            "description": "Se precisa de atendimento humano"
        }
    }
}

# Pre-built schemas for common use cases (INPUT)
PRESET_INPUT_SCHEMAS = {
    "church_member": {
        "nome_igreja": {"type": "string", "description": "Nome da igreja"},
        "nome_usuario": {"type": "string", "description": "Nome do membro"},
        "telefone": {"type": "string", "description": "Telefone do membro", "optional": True},
        "cargo": {"type": "string", "description": "Cargo na igreja", "optional": True}
    },
    "whatsapp_contact": {
        "nome": {"type": "string", "description": "Nome do contato"},
        "telefone": {"type": "string", "description": "Número do WhatsApp"},
        "plano": {"type": "string", "enum": ["basico", "premium"], "description": "Plano do cliente", "optional": True}
    },
    "student": {
        "nome_aluno": {"type": "string", "description": "Nome do aluno"},
        "turma": {"type": "string", "description": "Turma do aluno"},
        "instituicao": {"type": "string", "description": "Nome da instituição", "optional": True}
    }
}
