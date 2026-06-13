"""
Workflow Engine — Block-based pipeline executor for Basile

Executes workflows defined as a sequence of connected blocks.
Each block receives data from the accumulated context and produces output
that is stored back into the context for downstream blocks.

Supported block types:
  - trigger       : Entry point (webhook, manual, schedule)
  - http_request  : HTTP call without AI (pure automation)
  - if            : Conditional branching (true/false)
  - router        : Multi-path routing based on rules
  - filter        : Array filtering / data selection
  - agent         : Invoke a Basile AI agent
  - transform     : Data manipulation (set, merge, extract)
  - delay         : Pause execution for N milliseconds
  - python        : Execute arbitrary Python code with context access
  - mcp           : Call an MCP integration directly (HTTP/SSE/MCP protocol)
"""

import asyncio
import httpx
import json
import logging
import re
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.workflow import Workflow
from app.models.workflow_execution import WorkflowExecution

logger = logging.getLogger(__name__)


def make_json_safe(obj: Any, seen: Optional[set] = None) -> Any:
    """
    Recursively sanitize any Python object to make it completely JSON-safe,
    resolving circular references and converting non-serializable objects (UUIDs, datetimes, sets)
    to strings/primitives to prevent database flush errors.
    """
    if seen is None:
        seen = set()

    if obj is None:
        return None

    # Check for circular reference using object identity
    obj_id = id(obj)
    if obj_id in seen:
        return "[Circular Reference]"

    # Primitive types that are native to JSON
    if isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, UUID):
        return str(obj)

    if isinstance(obj, datetime):
        return obj.isoformat()

    if isinstance(obj, dict):
        seen.add(obj_id)
        # Avoid mutating the original dictionary
        safe_dict = {}
        for k, v in obj.items():
            safe_dict[str(k)] = make_json_safe(v, seen)
        seen.remove(obj_id)
        return safe_dict

    if isinstance(obj, (list, tuple, set)):
        seen.add(obj_id)
        safe_list = [make_json_safe(item, seen) for item in obj]
        seen.remove(obj_id)
        return safe_list

    if hasattr(obj, 'to_dict') and callable(getattr(obj, 'to_dict')):
        try:
            seen.add(obj_id)
            res = make_json_safe(obj.to_dict(), seen)
            seen.remove(obj_id)
            return res
        except Exception:
            return str(obj)

    # Fallback to string representation of the object
    return str(obj)



# ─────────────────────────────────────────────────────────────
# Template resolution
# ─────────────────────────────────────────────────────────────

_TEMPLATE_RE = re.compile(r'\{\{\s*(.+?)\s*\}\}')


def _resolve_path(data: Any, path: str) -> Any:
    """
    Walk a dot-separated path within *data*.

    Supports:
      - dict key access: ``a.b.c``
      - list indexing: ``items.0.name``
      - special ``length`` pseudo-key for lists/dicts/strings
    """
    current = data
    for part in path.split('.'):
        if current is None:
            return None
        if part == 'length' and isinstance(current, (list, dict, str)):
            return len(current)
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def resolve_template(template: Any, context: Dict[str, Any]) -> Any:
    """
    Resolve template strings like ``{{ $trigger.payload.leader_id }}``.

    If the entire string is a single template expression and the resolved
    value is a non-string (dict, list, int …), the raw value is returned
    rather than stringifying it — this preserves structure for JSON bodies.

    Supports:
      - ``{{ $trigger.payload.key }}``  → trigger payload
      - ``{{ $output_key.path }}``      → previous block output
      - ``{{ $env.VAR_NAME }}``         → environment variable
      - ``{{ $workflow.variables.key }}``→ workflow-level variables
    """
    if not isinstance(template, str):
        # Recursively resolve inside dicts and lists
        if isinstance(template, dict):
            return {k: resolve_template(v, context) for k, v in template.items()}
        if isinstance(template, list):
            return [resolve_template(item, context) for item in template]
        return template

    # Resolve global macros ({{ $now }}, {{ $now(format) }}) FIRST,
    # before context-variable resolution tries to look up $now as a key.
    if '{{ $now' in template:
        try:
            from app.utils.macros import resolve_global_macros
            trigger_data = context.get('$trigger', {}).get('payload', {})
            template = resolve_global_macros(template, trigger_data)
        except Exception:
            pass

    matches = list(_TEMPLATE_RE.finditer(template))
    if not matches:
        return template

    # Single-expression shortcut: return raw value (preserves type)
    if len(matches) == 1 and matches[0].group(0) == template.strip():
        expr = matches[0].group(1).strip()
        return _resolve_expression(expr, context)

    # Multi-expression or mixed text: stringify each replacement
    def _replace(m):
        expr = m.group(1).strip()
        val = _resolve_expression(expr, context)
        if val is None:
            return ''
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        return str(val)

    return _TEMPLATE_RE.sub(_replace, template)


def _resolve_list_macro(args_str: str, context: Dict[str, Any]) -> Optional[List[str]]:
    """Helper to parse list macro arguments and format list items."""
    if ',' in args_str:
        var_path, format_str_raw = args_str.split(',', 1)
        var_path = var_path.strip().lstrip('$')
        format_str_raw = format_str_raw.strip()
        temp = format_str_raw
        while (temp.startswith('"') and temp.endswith('"')) or (temp.startswith("'") and temp.endswith("'")):
            if len(temp) < 2:
                break
            temp = temp[1:-1]
        format_template = temp
    else:
        var_path = args_str.strip().lstrip('$')
        format_template = None

    parts = var_path.split('.', 1)
    root_key = parts[0]
    rest = parts[1] if len(parts) > 1 else None

    root_val = context.get(f'${root_key}') or context.get(root_key)
    val = _resolve_path(root_val, rest) if (root_val is not None and rest) else root_val

    if not isinstance(val, list):
        return None

    formatted_items = []
    for item in val:
        if format_template:
            if isinstance(item, dict):
                flat_item = {}
                def _flatten(d, parent_key=''):
                    for k, v in d.items():
                        new_key = f"{parent_key}.{k}" if parent_key else k
                        flat_item[new_key] = v
                        if isinstance(v, dict):
                            _flatten(v, new_key)
                _flatten(item)

                class SafeDict(dict):
                    def __missing__(self, key):
                        return ''
                try:
                    safe_item = SafeDict({k: (str(v) if v is not None else '') for k, v in flat_item.items()})
                    import re
                    res_str = format_template
                    placeholders = re.findall(r'\{([^}]+)\}', res_str)
                    for ph in placeholders:
                        val_str = safe_item[ph]
                        res_str = res_str.replace(f'{{{ph}}}', val_str)
                    formatted_items.append(res_str)
                except Exception:
                    formatted_items.append(str(item))
            else:
                if '{item}' in format_template:
                    formatted_items.append(format_template.replace('{item}', str(item)))
                else:
                    formatted_items.append(str(item))
        else:
            if isinstance(item, dict):
                pairs = [f"{k}: {v}" for k, v in item.items() if v is not None and str(v).strip() != '']
                formatted_items.append(", ".join(pairs))
            else:
                formatted_items.append(str(item))
    return formatted_items


def parse_typed_value(val_str: str) -> Any:
    """Tenta converter uma string para seu tipo correspondente (int, float, bool, list, dict).
    Se estiver entre aspas, remove as aspas e retorna como string pura."""
    val_str = val_str.strip()
    if not val_str:
        return val_str

    # Suporte case-insensitive para booleano antes de outros parsers
    if val_str.lower() == 'true':
        return True
    if val_str.lower() == 'false':
        return False

    # 1. Tentar parsear diretamente com json.loads (booleans, numbers, arrays, dicts com aspas duplas, null)
    try:
        return json.loads(val_str)
    except Exception:
        pass

    # 2. Tentar avaliar como literal Python (suporta strings de aspas simples, tuplas e estruturas similares)
    import ast
    try:
        evaluated = ast.literal_eval(val_str)
        # Converter tuplas em listas para padronização JSON
        if isinstance(evaluated, tuple):
            return list(evaluated)
        return evaluated
    except Exception:
        pass

    # 3. Se falhar, tentar envolver em colchetes para verificar se é uma lista delimitada por vírgulas (ex: "item1", "item2")
    try:
        return json.loads(f"[{val_str}]")
    except Exception:
        pass

    try:
        evaluated = ast.literal_eval(f"[{val_str}]")
        if isinstance(evaluated, tuple):
            return list(evaluated)
        return evaluated
    except Exception:
        pass

    # 4. Caso o valor esteja com aspas e falhou nas análises estruturadas (ex: string manual com aspas), remover aspas externas
    if (val_str.startswith('"') and val_str.endswith('"')) or (val_str.startswith("'") and val_str.endswith("'")):
        if len(val_str) >= 2:
            return val_str[1:-1]

    return val_str


def _resolve_expression(expr: str, context: Dict[str, Any]) -> Any:
    """Resolve a single template expression (without {{ }})."""
    if not expr.startswith('$'):
        return expr  # literal

    # Strip leading $
    path = expr[1:]

    # Handle $fromAI("key", "desc")
    if path.startswith('fromAI('):
        import ast
        args_str = path[7:-1]
        try:
            args = ast.literal_eval(f'({args_str},)')
            if args:
                name = args[0]
                trigger_payload = context.get('$trigger', {}).get('payload', {})
                return trigger_payload.get(name, '')
        except:
            return ''

    # Handle $list(path, "format")
    if path.startswith('list('):
        args_str = path[5:-1]
        items = _resolve_list_macro(args_str, context)
        if items is not None:
            return "\n".join(items)
        # Fallback se não for uma lista
        var_path = args_str.split(',', 1)[0].strip().lstrip('$') if ',' in args_str else args_str.strip().lstrip('$')
        parts = var_path.split('.', 1)
        root_key = parts[0]
        rest = parts[1] if len(parts) > 1 else None
        root_val = context.get(f'${root_key}') or context.get(root_key)
        val = _resolve_path(root_val, rest) if (root_val is not None and rest) else root_val
        return str(val) if val is not None else ''

    # Handle $join(path, "format")
    if path.startswith('join('):
        args_str = path[5:-1]
        items = _resolve_list_macro(args_str, context)
        if items is not None:
            return ",".join(json.dumps(item, ensure_ascii=False) for item in items)
        # Fallback se não for uma lista
        var_path = args_str.split(',', 1)[0].strip().lstrip('$') if ',' in args_str else args_str.strip().lstrip('$')
        parts = var_path.split('.', 1)
        root_key = parts[0]
        rest = parts[1] if len(parts) > 1 else None
        root_val = context.get(f'${root_key}') or context.get(root_key)
        val = _resolve_path(root_val, rest) if (root_val is not None and rest) else root_val
        return str(val) if val is not None else ''

    # $env.VAR_NAME → environment variable
    if path.startswith('env.'):
        import os
        return os.environ.get(path[4:], '')

    # Everything else → context lookup
    # The first segment is the context key (e.g. "trigger", "leader_data")
    parts = path.split('.', 1)
    root_key = parts[0]
    rest = parts[1] if len(parts) > 1 else None

    root_val = context.get(f'${root_key}') or context.get(root_key)
    if root_val is None:
        return None
    if rest is None:
        return root_val
    return _resolve_path(root_val, rest)


# ─────────────────────────────────────────────────────────────
# Comparison helpers for IF / Router / Filter
# ─────────────────────────────────────────────────────────────

def _coerce_numeric(val: Any) -> Optional[float]:
    """Try to cast *val* to float; return None on failure."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return None
    return None


def evaluate_condition(value_a: Any, operator: str, value_b: Any) -> bool:
    """Evaluate a comparison between two values."""
    op = operator.lower().strip()

    # Auto-resolve typed values if they are strings
    typed_a = parse_typed_value(value_a) if isinstance(value_a, str) else value_a
    typed_b = parse_typed_value(value_b) if isinstance(value_b, str) else value_b

    # String coercions for comparison based on typed values
    str_a = str(typed_a) if typed_a is not None else ''
    str_b = str(typed_b) if typed_b is not None else ''

    if op in ('equals', 'eq', '=='):
        return typed_a == typed_b
    if op in ('not_equals', 'neq', '!='):
        return typed_a != typed_b
    if op in ('contains',):
        return str_b in str_a
    if op in ('not_contains',):
        return str_b not in str_a
    if op in ('starts_with',):
        return str_a.startswith(str_b)
    if op in ('ends_with',):
        return str_a.endswith(str_b)
    if op in ('exists',):
        return typed_a is not None and str_a != ''
    if op in ('is_empty', 'not_exists'):
        return typed_a is None or str_a == '' or typed_a == [] or typed_a == {}

    # Numeric comparisons
    num_a = _coerce_numeric(typed_a)
    num_b = _coerce_numeric(typed_b)
    if num_a is not None and num_b is not None:
        if op in ('greater_than', 'gt', '>'):
            return num_a > num_b
        if op in ('greater_than_or_equal', 'gte', '>='):
            return num_a >= num_b
        if op in ('less_than', 'lt', '<'):
            return num_a < num_b
        if op in ('less_than_or_equal', 'lte', '<='):
            return num_a <= num_b

    # Fallback: string comparison for ordering ops
    if op in ('greater_than', 'gt', '>'):
        return str_a > str_b
    if op in ('less_than', 'lt', '<'):
        return str_a < str_b

    logger.warning(f"[WorkflowEngine] Unknown operator: {operator}")
    return False


# ─────────────────────────────────────────────────────────────
# Pausing and Resuming Execution Exception
# ─────────────────────────────────────────────────────────────

class WorkflowPauseException(Exception):
    """Exception raised when a workflow execution needs to be paused for human input."""
    def __init__(self, block_id: str):
        self.block_id = block_id
        super().__init__(f"Workflow paused at block {block_id}")


# ─────────────────────────────────────────────────────────────
# Main Engine
# ─────────────────────────────────────────────────────────────

class WorkflowEngine:
    """
    Executes a Basile workflow (block pipeline).

    Usage::

        engine = WorkflowEngine(db)
        result = await engine.execute(workflow_id, trigger_data)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Public API ─────────────────────────────────────────────

    async def execute(
        self,
        workflow_id: UUID,
        trigger_data: Dict[str, Any],
        trigger_type: str = "manual",
        recursion_depth: int = 0,
    ) -> Dict[str, Any]:
        """Execute a workflow from start to finish and return the final context."""
        if recursion_depth > 5:
            raise ValueError("Profundidade máxima de recursão de sub-workflows atingida (limite: 5)")

        t0 = time.time()
        # Load workflow
        result = await self.db.execute(select(Workflow).where(Workflow.id == workflow_id))
        workflow = result.scalar_one_or_none()
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        if not workflow.is_active:
            raise ValueError(f"Workflow '{workflow.name}' is inactive")

        definition = workflow.definition or {}
        blocks = {b['id']: b for b in definition.get('blocks', [])}
        edges = definition.get('edges', [])

        if not blocks:
            raise ValueError(f"Workflow '{workflow.name}' has no blocks defined")

        # Create execution record
        execution = WorkflowExecution(
            workflow_id=workflow_id,
            status="running",
            trigger_type=trigger_type,
            trigger_data=make_json_safe(trigger_data),
            context={},
            blocks_executed=[],
            blocks_total=len(blocks),
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(execution)
        await self.db.commit()
        await self.db.refresh(execution)

        # Initialize context
        context: Dict[str, Any] = {
            '$trigger': {'payload': trigger_data},
            '$workflow': {
                'id': str(workflow_id),
                'name': workflow.name,
                'variables': definition.get('variables', {}),
            },
        }
        blocks_log: List[Dict[str, Any]] = []

        try:
            # Find trigger block (entry point)
            trigger_block = self._find_trigger_block(blocks)
            if not trigger_block:
                raise ValueError("No trigger block found in workflow definition")

            current_block_id = trigger_block['id']

            return await self._run_execution_loop(
                execution=execution,
                context=context,
                current_block_id=current_block_id,
                blocks=blocks,
                edges=edges,
                blocks_log=blocks_log,
            )
        except Exception as e:
            execution.status = "failed"
            execution.error_message = f"{type(e).__name__}: {str(e)}"
            execution.blocks_executed = make_json_safe(blocks_log)
            execution.context = make_json_safe({k.lstrip('$'): v for k, v in context.items()})
            execution.completed_at = datetime.now(timezone.utc)
            execution.duration_ms = 0
            await self.db.commit()

            logger.error(f"[WorkflowEngine] ❌ Workflow '{workflow.name}' failed: {e}")
            traceback.print_exc()
            raise

    async def resume(
        self,
        execution_id: UUID,
        input_data: Any,
    ) -> Dict[str, Any]:
        """Resume a paused workflow execution with the provided input data."""
        # Load execution
        result = await self.db.execute(select(WorkflowExecution).where(WorkflowExecution.id == execution_id))
        execution = result.scalar_one_or_none()
        if not execution:
            raise ValueError(f"Workflow execution {execution_id} not found")
        if execution.status != "paused":
            raise ValueError(f"Workflow execution {execution_id} is not paused (status: {execution.status})")

        # Load workflow
        wf_result = await self.db.execute(select(Workflow).where(Workflow.id == execution.workflow_id))
        workflow = wf_result.scalar_one_or_none()
        if not workflow:
            raise ValueError(f"Workflow {execution.workflow_id} not found")

        definition = workflow.definition or {}
        blocks = {b['id']: b for b in definition.get('blocks', [])}
        edges = definition.get('edges', [])

        # Restore context and prefix $ keys
        context: Dict[str, Any] = {}
        for k, v in execution.context.items():
            if k.startswith('$'):
                context[k] = v
            else:
                context[f'${k}'] = v

        # Restore reference sharing for the trigger block output key
        trigger_block = self._find_trigger_block(blocks)
        if trigger_block:
            trigger_output_key = trigger_block.get('config', {}).get('output_key', trigger_block['id'])
            if '$trigger' in context:
                context[f'${trigger_output_key}'] = context['$trigger']

        # Check for cancel signal ("sair")
        is_cancel = False
        if isinstance(input_data, str) and input_data.strip().lower() == 'sair':
            is_cancel = True
        elif isinstance(input_data, dict):
            # Check system.button_response
            sys_data = input_data.get('system')
            if isinstance(sys_data, dict):
                btn_resp = sys_data.get('button_response')
                if isinstance(btn_resp, str) and btn_resp.strip().lower() == 'sair':
                    is_cancel = True
            
            # Fallback checks (e.g. global.button_response or direct message/button response)
            if not is_cancel:
                glob_data = input_data.get('global')
                if isinstance(glob_data, dict):
                    btn_resp = glob_data.get('button_response')
                    if isinstance(btn_resp, str) and btn_resp.strip().lower() == 'sair':
                        is_cancel = True
                
            if not is_cancel:
                msg_val = input_data.get('message')
                if isinstance(msg_val, str) and msg_val.strip().lower() == 'sair':
                    is_cancel = True

        if is_cancel:
            logger.info(f"[WorkflowEngine] 🛑 Workflow execution {execution_id} cancelled by user input ('sair')")
            execution.status = "cancelled"
            execution.error_message = "Execution cancelled by user ('sair')"
            execution.completed_at = datetime.now(timezone.utc)
            
            # Clean active session mapping in redis if applicable
            session_id = None
            if '$trigger' in context and isinstance(context['$trigger'], dict):
                session_id = context['$trigger'].get('payload', {}).get('session_id')
            if not session_id and isinstance(input_data, dict):
                session_id = input_data.get('session_id')
                
            if session_id:
                from app.redis_client import redis_client
                await redis_client.delete(f"active_workflow_run:{session_id}")
                
            await self.db.commit()
            
            clean_context = {k.lstrip('$'): v for k, v in context.items()}
            return {
                'status': 'cancelled',
                'execution_id': execution.id,
                'context': clean_context,
                'result': None,
            }

        # Merge new input_data into trigger payload so subsequent blocks and MCP tools can access it
        if '$trigger' in context and isinstance(context['$trigger'], dict):
            payload = context['$trigger'].get('payload')
            if not isinstance(payload, dict):
                payload = {}
                context['$trigger']['payload'] = payload

            if isinstance(input_data, dict):
                payload.update(input_data)
                
                # Try to parse 'message' as JSON and merge its fields if it is a dictionary
                msg_val = input_data.get('message')
                if isinstance(msg_val, str) and msg_val.strip():
                    try:
                        import json
                        parsed_msg = json.loads(msg_val)
                        if isinstance(parsed_msg, dict):
                            payload.update(parsed_msg)
                            payload['parsed_message'] = parsed_msg
                    except Exception:
                        pass
            else:
                payload['message'] = input_data
                if isinstance(input_data, str) and input_data.strip():
                    try:
                        import json
                        parsed_msg = json.loads(input_data)
                        if isinstance(parsed_msg, dict):
                            payload.update(parsed_msg)
                            payload['parsed_message'] = parsed_msg
                    except Exception:
                        pass


        # Set execution status to running
        execution.status = "running"
        await self.db.commit()

        paused_block_id = execution.current_block_id
        block = blocks.get(paused_block_id)
        if not block:
            raise ValueError(f"Paused block {paused_block_id} not found in workflow definition")

        output_key = block.get('config', {}).get('output_key', block['id'])
        
        # Save user response as the result of the paused block
        context[f'${output_key}'] = input_data
        
        blocks_log = execution.blocks_executed or []
        # Update or append the block log for the paused block
        block_log = {
            'block_id': paused_block_id,
            'block_type': block.get('type', 'wait_input'),
            'label': block.get('label', ''),
            'status': 'success',
            'output_key': output_key,
            'duration_ms': 0,
            'error': None,
        }
        blocks_log.append(block_log)

        # Resolve next block ID
        next_block_id = self._resolve_next(block, input_data, context, edges)
        
        logger.info(f"[WorkflowEngine] ▶️ Resuming workflow execution {execution_id} at block {next_block_id}")
        
        # Run execution loop starting from the next block
        return await self._run_execution_loop(
            execution=execution,
            context=context,
            current_block_id=next_block_id,
            blocks=blocks,
            edges=edges,
            blocks_log=blocks_log,
        )

    async def _run_execution_loop(
        self,
        execution: WorkflowExecution,
        context: Dict[str, Any],
        current_block_id: Optional[str],
        blocks: Dict[str, Dict[str, Any]],
        edges: List[Dict[str, Any]],
        blocks_log: List[Dict[str, Any]],
        recursion_depth: int = 0,
    ) -> Dict[str, Any]:
        t0 = time.time()
        # Find response block to check if we should store in memory
        store_in_memory = True
        for b in blocks.values():
            if b.get('type') == 'response':
                store_in_memory = b.get('config', {}).get('store_in_memory', True)
                break

        last_output_key = None
        # Try to find the last output key from existing context/blocks_log if resuming
        if blocks_log:
            for log in reversed(blocks_log):
                if log.get('status') == 'success' and log.get('output_key'):
                    last_output_key = log.get('output_key')
                    break

        try:
            while current_block_id:
                block = blocks.get(current_block_id)
                if not block:
                    # Fallback lookup: check if any block has output_key matching current_block_id
                    for b in blocks.values():
                        if b.get('config', {}).get('output_key') == current_block_id:
                            block = b
                            current_block_id = b['id']
                            break
                if not block:
                    logger.warning(f"[WorkflowEngine] Block '{current_block_id}' not found, stopping")
                    break

                # Update execution state
                execution.current_block_id = current_block_id
                await self.db.commit()

                # Execute block
                bt0 = time.time()
                block_result = None
                block_status = "success"
                block_error = None

                try:
                    block_result = await self._execute_block(block, context, recursion_depth, last_output_key)
                except WorkflowPauseException as pe:
                    total_duration = int((time.time() - t0) * 1000)
                    clean_context = {k.lstrip('$'): v for k, v in context.items()}
                    
                    current_result = None
                    if last_output_key:
                        current_result = context.get(f'${last_output_key}') or clean_context.get(last_output_key)
                        if isinstance(current_result, dict) and 'headers' in current_result and 'data' in current_result:
                            current_result = {k: v for k, v in current_result.items() if k != 'headers'}

                    execution.status = "paused"
                    execution.current_block_id = pe.block_id
                    execution.context = make_json_safe(clean_context)
                    execution.blocks_executed = make_json_safe(blocks_log)
                    execution.result = make_json_safe(current_result)
                    await self.db.commit()
                    
                    session_id = context.get('$trigger', {}).get('payload', {}).get('session_id')
                    if session_id:
                        from app.redis_client import redis_client
                        timeout_seconds = int(block.get('config', {}).get('timeout_seconds', 7200))
                        await redis_client.set(f"active_workflow_run:{session_id}", str(execution.id), expire=timeout_seconds)
                        logger.info(f"[WorkflowEngine] Mapped active_workflow_run:{session_id} to execution {execution.id} for {timeout_seconds}s")
                    
                    logger.info(f"[WorkflowEngine] ⏸️ Workflow execution {execution.id} paused at block {pe.block_id}")
                    return {
                        'status': 'paused',
                        'execution_id': execution.id,
                        'current_block_id': pe.block_id,
                        'context': clean_context,
                        'result': current_result,
                        'store_in_memory': store_in_memory,
                    }
                except Exception as e:
                    block_status = "failed"
                    block_error = str(e)
                    logger.error(f"[WorkflowEngine] Block '{current_block_id}' ({block.get('type')}) failed: {e}")

                    error_handling = block.get('config', {}).get('error_handling', 'stop')
                    if error_handling == 'stop':
                        raise
                    # 'continue' → proceed to next block

                block_duration = int((time.time() - bt0) * 1000)
                output_key = block.get('config', {}).get('output_key', block['id'])

                # Store result in context
                if block_result is not None and block_status == "success":
                    context[f'${output_key}'] = block_result
                    last_output_key = output_key

                # Log block execution
                block_log = {
                    'block_id': current_block_id,
                    'block_type': block.get('type', 'unknown'),
                    'label': block.get('label', ''),
                    'status': block_status,
                    'output_key': output_key,
                    'duration_ms': block_duration,
                    'error': block_error,
                }
                blocks_log.append(block_log)

                logger.info(
                    f"[WorkflowEngine] ✅ Block '{block.get('label', current_block_id)}' "
                    f"({block.get('type')}) → {block_status} ({block_duration}ms)"
                )

                # Determine next block
                next_block_id = self._resolve_next(
                    block, block_result, context, edges
                )
                current_block_id = next_block_id

            # Success
            total_duration = int((time.time() - t0) * 1000)
            clean_context = {k.lstrip('$'): v for k, v in context.items()}

            final_result = None
            if last_output_key:
                final_result = context.get(f'${last_output_key}') or clean_context.get(last_output_key)
                if isinstance(final_result, dict) and 'headers' in final_result and 'data' in final_result:
                    final_result = {k: v for k, v in final_result.items() if k != 'headers'}

            execution.status = "completed"
            execution.context = make_json_safe(clean_context)
            execution.blocks_executed = make_json_safe(blocks_log)
            execution.result = make_json_safe(final_result)
            execution.current_block_id = None
            execution.completed_at = datetime.now(timezone.utc)
            execution.duration_ms = (execution.duration_ms or 0) + total_duration
            await self.db.commit()

            # Clean active session mapping if completed
            session_id = context.get('$trigger', {}).get('payload', {}).get('session_id')
            if session_id:
                from app.redis_client import redis_client
                await redis_client.delete(f"active_workflow_run:{session_id}")

            logger.info(
                f"[WorkflowEngine] 🏁 Workflow execution {execution.id} completed "
                f"({len(blocks_log)} blocks, {execution.duration_ms}ms)"
            )
            return {
                'result': final_result,
                'context': clean_context,
                'status': 'completed',
                'last_block': last_output_key,
                'store_in_memory': store_in_memory,
            }

        except Exception as e:
            total_duration = int((time.time() - t0) * 1000)
            execution.status = "failed"
            execution.error_message = f"{type(e).__name__}: {str(e)}"
            execution.blocks_executed = make_json_safe(blocks_log)
            execution.context = make_json_safe({k.lstrip('$'): v for k, v in context.items()})
            execution.completed_at = datetime.now(timezone.utc)
            execution.duration_ms = (execution.duration_ms or 0) + total_duration
            await self.db.commit()

            # Clean active session mapping if failed
            session_id = context.get('$trigger', {}).get('payload', {}).get('session_id')
            if session_id:
                from app.redis_client import redis_client
                await redis_client.delete(f"active_workflow_run:{session_id}")

            logger.error(f"[WorkflowEngine] ❌ Workflow execution {execution.id} failed: {e}")
            traceback.print_exc()
            raise


    async def execute_single_block(
        self,
        block: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Any:
        """Execute a single block in isolation (for testing)."""
        return await self._execute_block(block, context)

    # ── Block executors ────────────────────────────────────────

    async def _execute_block(
        self,
        block: Dict[str, Any],
        context: Dict[str, Any],
        recursion_depth: int = 0,
        last_output_key: Optional[str] = None,
    ) -> Any:
        """Dispatch block execution by type."""
        block_type = block.get('type', '')
        config = block.get('config', {})

        match block_type:
            case 'trigger':
                return context.get('$trigger', {})
            case 'http_request':
                return await self._exec_http(config, context)
            case 'if':
                return await self._exec_if(config, context)
            case 'router':
                return await self._exec_router(config, context)
            case 'filter':
                return await self._exec_filter(config, context)
            case 'agent':
                return await self._exec_agent(config, context)
            case 'transform':
                return await self._exec_transform(config, context)
            case 'delay':
                return await self._exec_delay(config, context)
            case 'wait_input':
                raise WorkflowPauseException(block['id'])
            case 'sub_workflow':
                return await self._exec_sub_workflow(config, context, recursion_depth)
            case 'response':
                return await self._exec_response(config, context, last_output_key)
            case 'python':
                return await self._exec_python(config, context)
            case 'variables':
                return await self._exec_variables(config, context, block['id'])
            case 'mcp':
                return await self._exec_mcp(config, context)
            case _:
                raise ValueError(f"Unknown block type: {block_type}")

    async def _exec_response(
        self,
        config: Dict[str, Any],
        context: Dict[str, Any],
        last_output_key: Optional[str],
    ) -> Any:
        """Execute a response block, returning the last executed block's output."""
        if not last_output_key:
            return context.get('$trigger', {}).get('payload', {})
        val = context.get(f'${last_output_key}')
        if val is None:
            val = context.get(last_output_key)
        return val

    async def _exec_variables(self, config: Dict[str, Any], context: Dict[str, Any], block_id: str) -> Any:
        """Execute variables block to store/accumulate values."""
        output_key = config.get('output_key', block_id)
        
        # Obter estado anterior do context
        estado_anterior = context.get(f'${output_key}')
        if not isinstance(estado_anterior, dict):
            estado_anterior = {}
            
        estado_novo = {**estado_anterior}
        
        variables = config.get('variables', [])
        for var_def in variables:
            name = var_def.get('name')
            if not name:
                continue
                
            var_type = var_def.get('type', 'string')
            mode = var_def.get('mode', 'dynamic')
            
            if mode == 'fixed':
                val_raw = var_def.get('value')
                estado_novo[name] = self._coerce_type(val_raw, var_type)
            else:
                expr = var_def.get('expression', '')
                if expr:
                    val_resolved = resolve_template(expr, context)
                    if val_resolved is not None and val_resolved != '' and val_resolved != expr:
                        estado_novo[name] = self._coerce_type(val_resolved, var_type)
                    elif name not in estado_novo:
                        estado_novo[name] = self._get_default_value(var_type)
                elif name not in estado_novo:
                    estado_novo[name] = self._get_default_value(var_type)
                    
        return estado_novo

    def _coerce_type(self, val: Any, target_type: str) -> Any:
        if val is None:
            return self._get_default_value(target_type)
            
        if isinstance(val, str):
            val_parsed = parse_typed_value(val)
        else:
            val_parsed = val
            
        if target_type == 'string':
            return str(val_parsed)
        elif target_type == 'number':
            try:
                if '.' in str(val_parsed):
                    return float(val_parsed)
                return int(val_parsed)
            except:
                return 0
        elif target_type == 'boolean':
            if isinstance(val_parsed, str):
                return val_parsed.lower() in ('true', '1', 'yes')
            return bool(val_parsed)
        elif target_type == 'array':
            if isinstance(val_parsed, list):
                return val_parsed
            if val_parsed:
                return [val_parsed]
            return []
        elif target_type == 'object':
            if isinstance(val_parsed, dict):
                return val_parsed
            return {}
        return val_parsed

    def _get_default_value(self, target_type: str) -> Any:
        if target_type == 'array':
            return []
        elif target_type == 'object':
            return {}
        elif target_type == 'boolean':
            return False
        elif target_type == 'number':
            return 0
        return None

    async def _exec_http(self, config: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """Execute an HTTP request block."""
        method = resolve_template(config.get('method', 'GET'), context)
        url = resolve_template(config.get('url', ''), context)
        headers = resolve_template(config.get('headers', {}), context)
        body = resolve_template(config.get('body'), context)
        query_params = resolve_template(config.get('query_params', {}), context)
        timeout = float(config.get('timeout', 30))
        retry_count = int(config.get('retry_count', 0))

        # Auth handling
        auth_type = config.get('auth_type', 'none')
        auth_value = resolve_template(config.get('auth_value', ''), context)
        if auth_type == 'bearer' and auth_value:
            headers['Authorization'] = f'Bearer {auth_value}'
        elif auth_type == 'api_key' and auth_value:
            header_name = config.get('auth_header', 'X-API-Key')
            headers[header_name] = auth_value

        if not url:
            raise ValueError("HTTP Request block: 'url' is required")

        last_error = None
        for attempt in range(max(1, retry_count + 1)):
            try:
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    kwargs = {
                        'method': method.upper(),
                        'url': url,
                        'headers': headers,
                    }
                    if query_params:
                        kwargs['params'] = query_params
                    if body and method.upper() in ('POST', 'PUT', 'PATCH'):
                        if isinstance(body, (dict, list)):
                            kwargs['json'] = body
                        else:
                            kwargs['content'] = str(body)
                            if 'Content-Type' not in headers:
                                kwargs['headers']['Content-Type'] = 'application/json'

                    response = await client.request(**kwargs)

                    # Parse response
                    result: Dict[str, Any] = {
                        'status_code': response.status_code,
                        'headers': dict(response.headers),
                    }
                    try:
                        result['data'] = response.json()
                    except Exception:
                        result['data'] = response.text

                    if response.is_error:
                        result['error'] = True
                        logger.warning(
                            f"[WorkflowEngine] HTTP {method} {url} → {response.status_code}"
                        )
                    else:
                        logger.info(
                            f"[WorkflowEngine] HTTP {method} {url} → {response.status_code}"
                        )

                    # Apply response_mapping if configured
                    response_mapping = config.get('response_mapping')
                    if response_mapping and isinstance(response_mapping, dict):
                        try:
                            from app.services.mcp_tools import _apply_response_mapping
                            mapped = _apply_response_mapping(result, response_mapping)
                            result['data'] = mapped
                            logger.info(f"[WorkflowEngine] Response mapping applied: {list(mapped.keys())}")
                        except Exception as e:
                            logger.warning(f"[WorkflowEngine] Response mapping error: {e}")

                    return result

            except Exception as e:
                last_error = e
                if attempt < retry_count:
                    await asyncio.sleep(1 * (attempt + 1))  # backoff
                    logger.info(f"[WorkflowEngine] Retrying HTTP request (attempt {attempt + 2})")

        raise Exception(f"HTTP Request failed after {retry_count + 1} attempts: {last_error}")

    async def _exec_if(self, config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate an IF condition and return branch decision."""
        value_a = resolve_template(config.get('value_a'), context)
        value_b = resolve_template(config.get('value_b'), context)
        operator = config.get('operator', 'equals')

        result = evaluate_condition(value_a, operator, value_b)

        return {
            '_branch': 'true' if result else 'false',
            '_condition_result': result,
            'value_a': value_a,
            'value_b': value_b,
            'operator': operator,
        }

    async def _exec_router(self, config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate router rules and determine target(s)."""
        rules = config.get('rules', [])
        mode = config.get('mode', 'first_match')
        default_target = config.get('default_target')

        matched_targets = []
        matched_idx = -1
        any_matched = False

        for idx, rule in enumerate(rules):
            value_a = resolve_template(rule.get('value_a'), context)
            value_b = resolve_template(rule.get('value_b'), context)
            operator = rule.get('operator', 'equals')
            target = rule.get('target_block_id')

            if evaluate_condition(value_a, operator, value_b):
                any_matched = True
                matched_targets.append(target)
                if matched_idx == -1:
                    matched_idx = idx
                if mode == 'first_match':
                    break

        if not matched_targets and default_target:
            matched_targets = [default_target]

        # Determine branch label
        if mode == 'first_match':
            if matched_idx != -1:
                branch_label = f"rule_{matched_idx}"
            else:
                branch_label = "default"
        else: # all_matches
            branch_label = "match" if any_matched else "default"

        # Backwards compatibility: if rules still have target_block_id text configured (legacy),
        # fallback to returning the first matched target directly.
        legacy_target = matched_targets[0] if matched_targets else None

        return {
            '_branch': branch_label,
            '_legacy_target': legacy_target,
            '_all_matches': matched_targets,
            'mode': mode,
        }

    async def _exec_filter(self, config: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """Filter an array of data based on criteria."""
        source = resolve_template(config.get('source'), context)
        filter_field = config.get('filter_field', '')
        filter_operator = config.get('filter_operator', 'equals')
        filter_value = resolve_template(config.get('filter_value'), context)

        if not isinstance(source, list):
            logger.warning(f"[WorkflowEngine] Filter source is not a list: {type(source)}")
            return {'data': source, 'count': 0}

        filtered = []
        for item in source:
            if isinstance(item, dict):
                item_value = item.get(filter_field)
            else:
                item_value = item

            if evaluate_condition(item_value, filter_operator, filter_value):
                filtered.append(item)

        return {
            'data': filtered,
            'count': len(filtered),
            'original_count': len(source),
        }

    async def _exec_agent(self, config: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """Invoke a Basile AI agent within the workflow."""
        agent_id = resolve_template(config.get('agent_id', ''), context)
        message_template = config.get('message_template', '')
        context_mapping = config.get('context_mapping', {})
        session_id = resolve_template(
            config.get('session_id_source', 'workflow_auto'),
            context
        )
        use_structured = config.get('use_structured_output', False)
        user_access_level = resolve_template(
            config.get('user_access_level', 'normal'),
            context
        )

        if not agent_id:
            raise ValueError("Agent block: 'agent_id' is required")

        # Resolve message
        message = resolve_template(message_template, context)
        if not message:
            message = "Executar tarefa do workflow"

        # Build context_data for the agent
        context_data = {}
        for key, template in context_mapping.items():
            context_data[key] = resolve_template(template, context)

        # Inject workflow metadata
        context_data['_workflow_execution'] = True
        if config.get('inject_full_context', True):
            context_data['_workflow_context'] = {
                k.lstrip('$'): v for k, v in context.items()
                if k not in ('$workflow',)
            }
        else:
            context_data['_workflow_context'] = {}

        logger.info(f"[WorkflowEngine] 🤖 Invoking agent {agent_id} with message: {message[:100]}...")

        try:
            from app.worker.tasks import process_message_task

            result = await process_message_task(
                ctx={},
                message=message,
                session_id=session_id or f"wf_{agent_id}",
                agent_id=agent_id,
                user_access_level=user_access_level,
                context_data=context_data,
                transition_data=None,
                callback_url=None,
            )

            return {
                'response': result.get('response', ''),
                'agent_used': result.get('agent_used'),
                'transition_data': result.get('transition_data'),
                'last_agent': result.get('last_agent'),
            }

        except Exception as e:
            logger.error(f"[WorkflowEngine] Agent block failed: {e}")
            raise

    async def _exec_transform(self, config: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """Apply data transformation operations."""
        operations = config.get('operations', [])
        result: Dict[str, Any] = {}

        for op_def in operations:
            op = op_def.get('op', 'set')
            key = op_def.get('key', '')
            value = resolve_template(op_def.get('value'), context)
            if isinstance(value, str):
                value = parse_typed_value(value)

            if op == 'set':
                result[key] = value
            elif op == 'merge':
                if isinstance(value, dict) and isinstance(result.get(key), dict):
                    result[key] = {**result[key], **value}
                else:
                    result[key] = value
            elif op == 'extract':
                # Extract a specific path from context
                source = resolve_template(op_def.get('source'), context)
                path = op_def.get('path', '')
                result[key] = _resolve_path(source, path) if path else source
            elif op == 'map':
                # Map over a list and extract a field
                source = resolve_template(op_def.get('source'), context)
                field = op_def.get('field', '')
                if isinstance(source, list):
                    result[key] = [
                        item.get(field) if isinstance(item, dict) else item
                        for item in source
                    ]
                else:
                    result[key] = source
            elif op == 'flatten':
                source = resolve_template(op_def.get('source'), context)
                if isinstance(source, list):
                    flat = []
                    for item in source:
                        if isinstance(item, list):
                            flat.extend(item)
                        else:
                            flat.append(item)
                    result[key] = flat
                else:
                    result[key] = source
            elif op == 'join':
                source = resolve_template(op_def.get('source'), context)
                separator = op_def.get('separator', ', ')
                if isinstance(source, list):
                    result[key] = separator.join(str(s) for s in source)
                else:
                    result[key] = str(source) if source else ''
            elif op == 'stringify':
                result[key] = json.dumps(value, ensure_ascii=False) if value else ''
            elif op == 'parse_json':
                if isinstance(value, str):
                    try:
                        result[key] = json.loads(value)
                    except json.JSONDecodeError:
                        result[key] = value
                else:
                    result[key] = value

        # Resolve output type format configuration
        output_type = config.get('output_type', 'json')
        if output_type == 'text':
            text_template = config.get('text_template', '')
            return resolve_template(text_template, context)
            
        if output_type == 'raw_key':
            raw_key = config.get('raw_key', '')
            if raw_key in result:
                return result[raw_key]
            # Fallback if key not found in result
            return result

        return result

    async def _exec_delay(self, config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Pause execution for a specified duration."""
        delay_ms = config.get('delay_ms', 1000)
        if isinstance(delay_ms, str):
            delay_ms = resolve_template(delay_ms, context)
        delay_ms = int(delay_ms)

        # Cap at 5 minutes to prevent abuse
        delay_ms = min(delay_ms, 300_000)

        logger.info(f"[WorkflowEngine] ⏱️ Delay: {delay_ms}ms")
        await asyncio.sleep(delay_ms / 1000.0)

        return {
            'delayed_ms': delay_ms,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

    async def _exec_python(self, config: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Execute Python code block.

        The code has access to:
          - ``context``: the full workflow context dict (read-only recommended)
          - ``ctx``:     alias for context
          - standard builtins (no network/filesystem access by default)

        The code must assign the output to the variable ``result``.
        Example::

            members = ctx['$membros']['data']
            result = {'count': len(members), 'names': [m['name'] for m in members]}
        """
        code = config.get('code', '')
        if not code or not code.strip():
            return {'output': None, 'error': 'Nenhum código fornecido'}

        # Resolve templates inside the code (allows {{ $var }} interpolation)
        resolved_code = resolve_template(code, context)
        if not isinstance(resolved_code, str):
            resolved_code = code  # fallback if resolve changed type

        # Safe-ish sandbox: expose context, json, re, datetime utilities
        sandbox_globals = {
            '__builtins__': {
                # safe built-ins only
                'len': len, 'range': range, 'enumerate': enumerate,
                'zip': zip, 'map': map, 'filter': filter, 'sorted': sorted,
                'reversed': reversed, 'list': list, 'dict': dict, 'set': set,
                'tuple': tuple, 'str': str, 'int': int, 'float': float,
                'bool': bool, 'type': type, 'isinstance': isinstance,
                'hasattr': hasattr, 'getattr': getattr, 'setattr': setattr,
                'print': print, 'repr': repr, 'abs': abs, 'round': round,
                'min': min, 'max': max, 'sum': sum, 'any': any, 'all': all,
                'None': None, 'True': True, 'False': False,
            },
            'json': json,
            're': re,
            'datetime': datetime,
            'context': context,
            'ctx': context,
        }
        local_vars: Dict[str, Any] = {}

        try:
            exec(resolved_code, sandbox_globals, local_vars)  # noqa: S102
        except Exception as exc:
            tb = traceback.format_exc()
            logger.warning(f"[WorkflowEngine] Python block error: {exc}\n{tb}")
            return {'output': None, 'error': str(exc), 'traceback': tb}

        # The code should assign to `result`
        output = local_vars.get('result', local_vars)
        return make_json_safe(output)

    async def _exec_mcp(self, config: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Execute an MCP integration block.

        Config keys:
          - mcp_id       : UUID of the MCP to execute
          - params       : dict with $fromAI values (manually filled)
          - variables    : dict with $request.xxx context values (dot-path keys)
        """
        from uuid import UUID
        from sqlalchemy import select as sa_select
        from app.models.mcp import MCP
        from app.api.mcp import execute_http, execute_sse
        from app.services.mcp_tools import _inject_from_ai_params, _inject_request_params
        import urllib.parse

        mcp_id_str = config.get('mcp_id')
        if not mcp_id_str:
            raise ValueError("MCP block: 'mcp_id' é obrigatório")

        # Support template in mcp_id
        mcp_id_str = resolve_template(mcp_id_str, context)

        try:
            mcp_id = UUID(str(mcp_id_str))
        except Exception:
            raise ValueError(f"MCP block: mcp_id inválido: '{mcp_id_str}'")

        # Load MCP from DB
        result = await self.db.execute(sa_select(MCP).where(MCP.id == mcp_id))
        mcp = result.scalar_one_or_none()
        if not mcp:
            raise ValueError(f"MCP block: MCP '{mcp_id_str}' não encontrado")
        if not mcp.is_active:
            raise ValueError(f"MCP block: MCP '{mcp.name}' está inativo")

        # Build params — resolve templates in the param values
        raw_params = config.get('params', {})
        params: Dict[str, Any] = {}
        for k, v in raw_params.items():
            resolved_v = resolve_template(v, context)
            params[k] = resolved_v

        # Build variables (dot-path keys for $request.xxx)
        raw_variables = config.get('variables', {})
        variables: Dict[str, Any] = {}
        for k, v in raw_variables.items():
            resolved_v = resolve_template(v, context)
            variables[k] = resolved_v

        timeout = float(mcp.timeout_seconds or 30)
        protocol = (mcp.protocol or 'http').lower()

        logger.info(
            f"[WorkflowEngine] 🔌 MCP block: '{mcp.name}' protocol={protocol} "
            f"params={list(params.keys())} vars={list(variables.keys())}"
        )

        try:
            if protocol == 'http':
                result_data = await execute_http(mcp, params, timeout, variables=variables)
            elif protocol == 'sse':
                sse_result = await execute_sse(mcp, params, timeout, variables=variables)
                result_data = sse_result.get('result')
            elif protocol == 'mcp':
                from app.services.mcp_client import execute_mcp_protocol
                import json
                # Build body injecting params
                body_str = json.dumps(mcp.body_template or {})
                headers_str = json.dumps(mcp.headers or {})
                endpoint_str = urllib.parse.unquote(mcp.endpoint or '')
                query_str = json.dumps(getattr(mcp, 'query_template', {}) or {})

                if variables:
                    def _unflatten(flat: dict) -> dict:
                        res = {}
                        for fk, fv in flat.items():
                            parts = fk.split('.')
                            d = res
                            for p in parts[:-1]:
                                d = d.setdefault(p, {})
                            d[parts[-1]] = fv
                        return res
                    test_ctx = _unflatten(variables)
                    endpoint_str = _inject_request_params(endpoint_str, test_ctx)
                    body_str = _inject_request_params(body_str, test_ctx)
                    headers_str = _inject_request_params(headers_str, test_ctx)
                    query_str = _inject_request_params(query_str, test_ctx)

                body_str, _ = _inject_from_ai_params(body_str, params)
                headers_str, _ = _inject_from_ai_params(headers_str, params)
                endpoint_str, _ = _inject_from_ai_params(endpoint_str, params)
                query_str, _ = _inject_from_ai_params(query_str, params)

                body = json.loads(body_str)
                query_params_mcp = json.loads(query_str)
                for key in ['user_id', 'session_id']:
                    if key in body:
                        query_params_mcp[key] = body.pop(key)

                action = params.get('_action', 'call_tool')
                tool_name = params.get('_tool_name')
                tool_args = {k: v for k, v in params.items() if not k.startswith('_')}

                mcp_result = await execute_mcp_protocol(
                    endpoint=endpoint_str,
                    headers=json.loads(headers_str),
                    query_params=query_params_mcp,
                    action=action,
                    tool_name=tool_name,
                    tool_args=tool_args or None,
                    timeout=timeout,
                )
                if not mcp_result.get('success'):
                    raise Exception(mcp_result.get('error', 'MCP execution failed'))
                result_data = mcp_result.get('result')
            else:
                raise ValueError(f"MCP block: protocolo '{protocol}' não suportado")

            return make_json_safe(result_data)

        except Exception as exc:
            logger.error(f"[WorkflowEngine] MCP block '{mcp.name}' error: {exc}")
            raise

    async def _exec_sub_workflow(self, config: Dict[str, Any], context: Dict[str, Any], recursion_depth: int) -> Any:
        """Execute a sub-workflow as a nested block."""
        workflow_id_str = config.get('workflow_id')
        if not workflow_id_str:
            raise ValueError("Sub-workflow block: Nenhum workflow selecionado")

        try:
            workflow_id = UUID(resolve_template(workflow_id_str, context))
        except ValueError:
            # Try parsing dynamic ID from variable if stored as raw UUID or string
            resolved_id = resolve_template(workflow_id_str, context)
            try:
                workflow_id = UUID(resolved_id)
            except Exception:
                raise ValueError(f"Sub-workflow block: ID do workflow inválido: '{resolved_id}'")

        payload_mode = config.get('payload_mode', 'full')
        if payload_mode == 'custom':
            raw_payload = config.get('payload_template', '{}')
            # Resolve templates inside payload
            payload = resolve_template(raw_payload, context)
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    # Fallback to string wrapper if it's not valid JSON
                    payload = {"text": payload}
        else:
            # Pass the parent's trigger payload directly so the sub-workflow
            # gets the exact same $trigger.payload structure.
            payload = context.get('$trigger', {}).get('payload', {})

        logger.info(f"[WorkflowEngine] 🔀 Running sub-workflow: {workflow_id} (depth: {recursion_depth + 1})")
        
        # Run sub-workflow using the same DB session
        sub_engine = WorkflowEngine(self.db)
        sub_result = await sub_engine.execute(
            workflow_id=workflow_id,
            trigger_data=payload,
            trigger_type="sub_workflow",
            recursion_depth=recursion_depth + 1
        )
        
        return sub_result.get('result')

    # ── Navigation helpers ─────────────────────────────────────

    def _find_trigger_block(self, blocks: Dict[str, Dict]) -> Optional[Dict]:
        """Find the trigger block (entry point)."""
        for block in blocks.values():
            if block.get('type') == 'trigger':
                return block
        # Fallback: first block in order
        if blocks:
            return next(iter(blocks.values()))
        return None

    def _resolve_next(
        self,
        block: Dict[str, Any],
        block_result: Any,
        context: Dict[str, Any],
        edges: List[Dict[str, Any]],
    ) -> Optional[str]:
        """Determine the next block ID based on edges and branch logic."""
        block_id = block['id']
        block_type = block.get('type', '')

        # IF / Router blocks: use _branch from result to pick the right edge
        if block_type in ('if', 'router') and isinstance(block_result, dict):
            branch_label = block_result.get('_branch')

            if block_type == 'if':
                # Look for edge with matching label or sourceHandle (true/false)
                for edge in edges:
                    edge_handle = edge.get('sourceHandle') or edge.get('label')
                    if edge.get('source') == block_id and edge_handle == branch_label:
                        return edge['target']

                # Fallback: check config true_branch / false_branch
                config = block.get('config', {})
                if branch_label == 'true':
                    target = config.get('true_branch')
                    if target:
                        return target
                else:
                    target = config.get('false_branch')
                    if target:
                        return target

            elif block_type == 'router' and branch_label:
                # 1. Search for edge matching the handle (e.g. sourceHandle/label = 'rule_0' or 'match'/'default')
                for edge in edges:
                    edge_handle = edge.get('sourceHandle') or edge.get('label')
                    if edge.get('source') == block_id and edge_handle == branch_label:
                        return edge['target']

                # 2. Backwards compatibility: fallback to checking if there is an edge matching legacy target_block_id
                legacy_target = block_result.get('_legacy_target')
                if legacy_target:
                    for edge in edges:
                        if edge.get('source') == block_id and edge.get('target') == legacy_target:
                            return legacy_target

                # 3. Fallback: if branch_label happens to be the block ID itself
                for edge in edges:
                    if edge.get('source') == block_id and edge.get('target') == branch_label:
                        return branch_label

        # Standard: follow edge from this block (no label or first available)
        for edge in edges:
            if edge.get('source') == block_id:
                label = edge.get('label', '')
                source_handle = edge.get('sourceHandle') or label
                # Ignore edges that belong to specific conditional handles (true, false, match, default, rule_x)
                if source_handle in ('true', 'false', 'match', 'default') or (source_handle and source_handle.startswith('rule_')):
                    continue
                if not label or label == '':
                    return edge['target']

        # Check block's own 'next' array
        next_list = block.get('next', [])
        if next_list:
            return next_list[0]

        return None  # End of pipeline
