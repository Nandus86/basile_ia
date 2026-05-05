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


def _resolve_expression(expr: str, context: Dict[str, Any]) -> Any:
    """Resolve a single template expression (without {{ }})."""
    if not expr.startswith('$'):
        return expr  # literal

    # Strip leading $
    path = expr[1:]

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

    # String coercions for comparison
    str_a = str(value_a) if value_a is not None else ''
    str_b = str(value_b) if value_b is not None else ''

    if op in ('equals', 'eq', '=='):
        return str_a == str_b
    if op in ('not_equals', 'neq', '!='):
        return str_a != str_b
    if op in ('contains',):
        return str_b in str_a
    if op in ('not_contains',):
        return str_b not in str_a
    if op in ('starts_with',):
        return str_a.startswith(str_b)
    if op in ('ends_with',):
        return str_a.endswith(str_b)
    if op in ('exists',):
        return value_a is not None and str_a != ''
    if op in ('is_empty', 'not_exists'):
        return value_a is None or str_a == '' or value_a == [] or value_a == {}

    # Numeric comparisons
    num_a = _coerce_numeric(value_a)
    num_b = _coerce_numeric(value_b)
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
    ) -> Dict[str, Any]:
        """Execute a workflow from start to finish and return the final context."""
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
            trigger_data=trigger_data,
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

            while current_block_id:
                block = blocks.get(current_block_id)
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
                    block_result = await self._execute_block(block, context)
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
            # Remove internal $ keys for cleaner result
            clean_result = {k.lstrip('$'): v for k, v in context.items()}

            execution.status = "completed"
            execution.context = clean_result
            execution.blocks_executed = blocks_log
            execution.result = clean_result
            execution.current_block_id = None
            execution.completed_at = datetime.now(timezone.utc)
            execution.duration_ms = total_duration
            await self.db.commit()

            logger.info(
                f"[WorkflowEngine] 🏁 Workflow '{workflow.name}' completed "
                f"({len(blocks_log)} blocks, {total_duration}ms)"
            )
            return clean_result

        except Exception as e:
            total_duration = int((time.time() - t0) * 1000)
            execution.status = "failed"
            execution.error_message = f"{type(e).__name__}: {str(e)}"
            execution.blocks_executed = blocks_log
            execution.context = {k.lstrip('$'): v for k, v in context.items()}
            execution.completed_at = datetime.now(timezone.utc)
            execution.duration_ms = total_duration
            await self.db.commit()

            logger.error(f"[WorkflowEngine] ❌ Workflow '{workflow.name}' failed: {e}")
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

    async def _execute_block(self, block: Dict[str, Any], context: Dict[str, Any]) -> Any:
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
            case _:
                raise ValueError(f"Unknown block type: {block_type}")

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
        for rule in rules:
            value_a = resolve_template(rule.get('value_a'), context)
            value_b = resolve_template(rule.get('value_b'), context)
            operator = rule.get('operator', 'equals')
            target = rule.get('target_block_id')

            if evaluate_condition(value_a, operator, value_b):
                matched_targets.append(target)
                if mode == 'first_match':
                    break

        if not matched_targets and default_target:
            matched_targets = [default_target]

        return {
            '_branch': matched_targets[0] if matched_targets else None,
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
        context_data['_workflow_context'] = {
            k.lstrip('$'): v for k, v in context.items()
            if k not in ('$workflow',)
        }

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
                # Look for edge with matching label (true/false)
                for edge in edges:
                    if edge.get('source') == block_id and edge.get('label') == branch_label:
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
                return branch_label  # Router stores the block_id directly

        # Standard: follow edge from this block (no label or first available)
        for edge in edges:
            if edge.get('source') == block_id:
                label = edge.get('label', '')
                if not label or label == '':
                    return edge['target']

        # Check block's own 'next' array
        next_list = block.get('next', [])
        if next_list:
            return next_list[0]

        return None  # End of pipeline
