# Fix: Colaboradores como Sub-graph Nodes no caminho real (branch 0.0.245)

## Contexto

Na branch `0.0.243`, o commit `dce9998` tentou migrar os colaboradores de "tool wrapper" para "nós nativos de Sub-graph" no LangGraph, mas a lógica foi adicionada em um método morto. Sintoma: o output final era literalmente `[INTERCEPT_REQUIRED] BasileIA - Agente de Relatorios`.

### Causa raiz (confirmada)

- `backend/app/orchestrator/agent_factory.py` tem **duas** definições de `invoke_agent`:
  - Linha 661: método SOBRESCRITO pelo segundo (nunca executa). Foi onde o `dce9998` adicionou os sub-graph nodes.
  - Linha 1498: método real, delega para `_prepare_agent_run` (linha 1256).
- `_prepare_agent_run` (caminho usado por `invoke_agent`, `invoke_agent_with_trace`, `invoke_agent_stream`) **não tem** os nós de colaboradores nem o intercept no `should_continue_edge` (linha 1453, só retorna `"tools"`/`"force_end"`/`END`).
- O `dce9998` também esvaziou a tool `consultar_X` em `tasks.py` para retornar o sinalizador `[INTERCEPT_REQUIRED] {nome}`. Sem intercept no caminho real, o `ToolNode` executa a tool, e o sinalizador vira resposta final.

### Decisões tomadas

1. Reintroduzir a migração para sub-graph nodes, mas **no `_prepare_agent_run`** (caminho real).
2. **Remover** a primeira `invoke_agent` morta (linhas 661-1175) — aprovado pelo usuário.
3. Portar o `route_after_tools` (bypass do always_end, commit `954f5a9`) do código morto para o `_prepare_agent_run` — hoje a feature está inativa no caminho real.
4. Corrigir bugs latentes do `dce9998`:
   - `history=list(state["messages"])` passado ao `CollaboratorExecutor.invoke` → **TypeError** (parâmetro não existe na assinatura).
   - Tratamento de `"__direct_payload"` na resposta do executor (existia na tool da 0.0.242, foi perdido).
   - Budget de collab nunca consumido (o guard da tool não roda porque o intercept desvia antes do `ToolNode`).

## Mudanças por arquivo

### 1. `backend/app/worker/tasks.py`

**`_build_collaborator_tools` (linha 1226):**
- Assinatura de retorno: `tuple[list, list, list, list, list]` → `tuple[list, list, list, list, list, list]`.
- Early returns (linhas 1251, 1268, 1283): adicionar um 6º elemento `[]`.
- Substituir o corpo de `_invoke_collab` (linhas 1386-1472) pelo sinalizador:
  ```python
  def _make_collab_invoker(_agent):
      async def _invoke_collab(instrucao: str) -> str:
          # O nó de orquestração interceptará a chamada antes do ToolNode.
          # Se por acaso cair aqui, retornamos uma string sinalizadora.
          return f"[INTERCEPT_REQUIRED] {_agent.name}"
      return _invoke_collab
  ```
- Chamada `invoker = _make_collab_invoker(...)` (linha 1475): reduzir para apenas `_agent=collab` (remover `_database`, `_ctx`, `_planner_enabled`, `_p_prompt`, `_p_model`, `_r_style`, `_parent_config`).
- Retorno final (linha 1497): `return tools, mandatory_instructions, deterministic_matches, always_start, always_end, all_collaborators`.

**`_enrich_agent_prompt` (linha 663):**
- Desempacotar 6 valores: `collab_tools, mandatory_instructions, deterministic_matches, always_start, always_end, all_collaborators`.
- Dentro de `if collab_tools:` (linha 723), adicionar:
  ```python
  agent_config["collaborators_list"] = all_collaborators
  ```

### 2. `backend/app/orchestrator/agent_orchestrator.py`

**Linha 619:**
- Desempacotar 6 valores: `collab_tools, mandatory_instructions, _, _, _, all_collaborators`.
- Dentro de `if collab_tools:` (linha 622), adicionar:
  ```python
  agent_config["collaborators_list"] = all_collaborators
  ```

### 3. `backend/app/orchestrator/agent_factory.py`

**Remover a primeira `invoke_agent` morta (linhas 661-1175):**
- Apagar do `async def invoke_agent(` (linha 661) até a linha anterior a `async def _prepare_agent_run(` (linha 1256).
- Mantém intactos: `_get_dynamic_skills_prompt`, `_prepare_agent_run` e as funções seguintes.

**`_prepare_agent_run` (após `force_end_node`, antes da montagem do graph em ~linha 1476):**
- Ler `collaborators_list = agent_config.get("collaborators_list", [])`.
- Criar `collab_node_names = []` e `make_collab_node(collab_agent, c_name)`:
  - Extrai a tool call da última mensagem (`tc["name"] == c_name`), pega `instrucao = tc["args"].get("instrucao", "")`.
  - **Budget:** antes de invocar, `if not budget.can_continue(): return ToolMessage de bloqueio` e `budget.consume("collab")`.
  - Invocar `CollaboratorExecutor(db=self.db).invoke(collaborator=..., instruction=..., session_id=context_data.get("session_id") if context_data else None, context_data=context_data, response_style=getattr(collab_agent, "response_style", "structured"))` — **SEM** `history=` e **SEM** `primary_agent`.
  - **`__direct_payload`:** se o response contiver `"__direct_payload"`, parsear e setar `agent_config["__direct_payload_result"] = parsed`.
  - Retornar `{"messages": [ToolMessage(content=response, tool_call_id=tc["id"], name=tc["name"])]}`.
- Loop por `collaborators_list` gerando `t_name = consultar_{safe_name}` e `c_node_name = collab_{safe_name}`:
  ```python
  agent_graph.add_node(c_node_name, make_collab_node(collab, t_name))
  agent_graph.add_edge(c_node_name, "agent")
  ```

**`should_continue_edge` (linha 1453):**
- No início, adicionar `if agent_config.get("__direct_payload_result"): return END`.
- Antes do `return "tools"`, adicionar o intercept:
  ```python
  for tc in last_msg.tool_calls:
      for t_name, c_node_name in collab_node_names:
          if tc["name"] == t_name:
              logger.info(f"[AgentFactory] 🔀 Routing to Sub-graph Node: {c_node_name}")
              return c_node_name
  ```

**Montagem do graph (linhas 1476-1483):**
- Substituir `agent_graph.add_conditional_edges("agent", should_continue_edge, ["tools", "force_end", END])` por:
  ```python
  valid_destinations = ["tools", "force_end", END] + [c[1] for c in collab_node_names]
  agent_graph.add_conditional_edges("agent", should_continue_edge, valid_destinations)
  ```
- Substituir `agent_graph.add_edge("tools", "agent")` pelo `route_after_tools` (portado da primeira invoke_agent):
  ```python
  def route_after_tools(state: AgentExecState) -> str:
      for msg in reversed(state["messages"]):
          if getattr(msg, "type", "") != "tool":
              break
          if getattr(msg, "name", None) in always_end_queue:
              logger.info(f"[AgentFactory] 🏁 Tool de saída final '{msg.name}' concluída. Encerrando o orquestrador.")
              return END
      return "agent"
  agent_graph.add_conditional_edges("tools", route_after_tools, ["agent", END])
  ```

## Observações

- Os 2 únicos consumidores de `_build_collaborator_tools` são `tasks.py:663` e `agent_orchestrator.py:619` (confirmado por grep) — ambos atualizados.
- As tools `consultar_X` permanecem em `selected_tools` (guardadas). O intercept no `should_continue_edge` desvia antes do `ToolNode`; se algum caminho cair no ToolNode, o sinalizador indica bug (como era a intenção do `dce9998`).
- O `budget.consume("collab")` no nó mantém o `max_collab_calls_per_turn` efetivo (bug latente do `dce9998`).
- NÃO há testes automatizados no backend (`backend/tests` não existe) — validação manual abaixo.

## Validação

1. Sintaxe/imports:
   - `python -m py_compile backend/app/orchestrator/agent_factory.py backend/app/worker/tasks.py backend/app/orchestrator/agent_orchestrator.py`
   - Import do módulo: `python -c "import sys; sys.path.insert(0, 'backend'); from app.orchestrator.agent_factory import AgentFactory; print('OK')"` (pode exigir env vars/deps instaladas).
2. Smoke test manual (com stack rodando):
   - Configurar um orquestrador com colaborador "BasileIA - Agente de Relatorios" habilitado.
   - Enviar mensagem que dispare a tool `consultar_...`.
   - Verificar nos logs: `🔀 Routing to Sub-graph Node: collab_...` e `🚀 Executing Sub-graph Node for '...'`.
   - Confirmar que o output final é a resposta sintetizada pelo orquestrador e que **NÃO** contém `[INTERCEPT_REQUIRED]`.
3. Testar cenário always_end: com colaborador `ALWAYS_ACTIVE_END`, confirmar que após a tool final o graph encerra (`🏁 Tool de saída final ... Encerrando o orquestrador`).
4. Testar cenário `__direct_payload`: colaborador que responde JSON com `__direct_payload` → confirmar que o LLM é pulado.

## Riscos

- Remoção de ~515 linhas: mitigado porque a primeira `invoke_agent` é inacessível (sobrescrita pela segunda); validação por `py_compile` + smoke test.
- Mudança de comportamento: o bypass do always_end passa a valer no caminho real (feature pretendida do `954f5a9`, hoje inativa).
- Não commitar sem solicitação explícita do usuário.
