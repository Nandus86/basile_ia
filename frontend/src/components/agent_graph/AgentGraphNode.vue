<template>
  <div
    :class="[
      'agent-graph-node',
      `node-type-${data.type || 'agent'}`,
      {
        'node-active-highlight': data?._isActive,
        'node-error-highlight': data?._hasError,
        'node-executed': data?._isExecuted
      }
    ]"
    @dblclick="$emit('edit', id)"
  >
    <!-- Top colored bar according to node category -->
    <div class="node-accent-bar" :style="{ backgroundColor: nodeColor }"></div>

    <div class="node-content pa-3">
      <!-- Header with Icon & Title -->
      <div class="d-flex align-center justify-space-between mb-1">
        <div class="d-flex align-center ga-2">
          <div class="node-icon-wrapper" :style="{ backgroundColor: nodeColor + '20', color: nodeColor }">
            <v-icon size="18">{{ nodeIcon }}</v-icon>
          </div>
          <div class="d-flex flex-column" style="min-width: 0;">
            <span class="node-title font-weight-bold text-truncate" style="max-width: 150px;" :title="label || data.label || meta.label">
              {{ label || data.label || meta.label }}
            </span>
            <span class="node-badge" :style="{ color: nodeColor }">
              {{ meta.label }}
            </span>
          </div>
        </div>

        <!-- Status chip if running or executed -->
        <v-chip v-if="data?._status" :color="statusColor" size="x-small" variant="flat" class="ml-1">
          {{ data._status }}
        </v-chip>
      </div>

      <!-- Node Subtitle / Agent & Block details -->
      <div class="node-details mt-2">
        <!-- Specialist Agent or Inline Agent info -->
        <div v-if="data.type === 'agent'">
          <!-- Inline Clean Agent -->
          <div v-if="isInlineAgent" class="d-flex flex-column ga-1">
            <div class="d-flex align-center ga-1 text-caption text-medium-emphasis">
              <v-icon size="14" color="teal">mdi-pencil-plus</v-icon>
              <span class="text-truncate font-weight-medium text-teal" style="max-width: 160px;">
                {{ data.config?.inline_agent?.name || 'Agente Limpo' }}
              </span>
            </div>
            <div class="d-flex align-center ga-1 flex-wrap mt-1">
              <v-chip size="x-small" variant="outlined" color="teal" density="compact">
                {{ data.config?.inline_agent?.model || 'gpt-4o-mini' }}
              </v-chip>
              <v-chip
                v-if="data.config?.inline_agent?.mcp_ids?.length"
                size="x-small"
                variant="tonal"
                color="info"
                density="compact"
                title="MCPs conectados"
              >
                {{ data.config?.inline_agent?.mcp_ids?.length }} MCPs
              </v-chip>
              <v-chip
                v-if="data.config?.inline_agent?.skill_ids?.length"
                size="x-small"
                variant="tonal"
                color="indigo"
                density="compact"
                title="Skills ativas"
              >
                {{ data.config?.inline_agent?.skill_ids?.length }} Skills
              </v-chip>
              <v-chip
                v-if="data.config?.context_mapping && Object.keys(data.config.context_mapping).length"
                size="x-small"
                variant="tonal"
                color="cyan"
                density="compact"
                title="Payload Schema / Context Mapping"
              >
                <v-icon start size="10">mdi-code-json</v-icon>Schema
              </v-chip>
              <v-chip
                v-if="data.config?.use_structured_output"
                size="x-small"
                variant="tonal"
                color="amber-darken-2"
                density="compact"
                title="Saída Estruturada (JSON)"
              >
                <v-icon start size="10">mdi-code-brackets</v-icon>JSON
              </v-chip>
              <v-chip
                v-if="data.config?.load_stm !== false && data.config?.load_stm !== undefined"
                size="x-small"
                variant="tonal"
                color="teal"
                density="compact"
                title="Lê Memória STM (Redis)"
              >
                STM
              </v-chip>
              <v-chip
                v-if="data.config?.load_mtm !== false && data.config?.load_mtm !== undefined"
                size="x-small"
                variant="tonal"
                color="indigo"
                density="compact"
                title="Lê Memória MTM (Postgres)"
              >
                MTM
              </v-chip>
              <v-chip
                v-if="data.config?.save_to_memory !== false && data.config?.save_to_memory !== undefined"
                size="x-small"
                variant="tonal"
                color="success"
                density="compact"
                title="Grava resposta na Memória (Chat)"
              >
                💾 Salva
              </v-chip>
            </div>
          </div>

          <!-- Existing System Agent -->
          <div v-else class="d-flex flex-column ga-1">
            <div class="d-flex align-center ga-1 text-caption text-medium-emphasis">
              <v-icon size="14" color="grey">mdi-account-tie</v-icon>
              <span class="text-truncate" style="max-width: 160px;">
                {{ data.config?.agent_name || 'Selecione um agente...' }}
              </span>
            </div>
            <div class="d-flex align-center ga-1 flex-wrap mt-1">
              <v-chip
                v-if="data.config?.context_mapping && Object.keys(data.config.context_mapping).length"
                size="x-small"
                variant="tonal"
                color="cyan"
                density="compact"
                title="Payload Schema / Context Mapping"
              >
                <v-icon start size="10">mdi-code-json</v-icon>Schema
              </v-chip>
              <v-chip
                v-if="data.config?.use_structured_output"
                size="x-small"
                variant="tonal"
                color="amber-darken-2"
                density="compact"
                title="Saída Estruturada (JSON)"
              >
                <v-icon start size="10">mdi-code-brackets</v-icon>JSON
              </v-chip>
              <v-chip
                v-if="data.config?.load_stm !== false && data.config?.load_stm !== undefined"
                size="x-small"
                variant="tonal"
                color="teal"
                density="compact"
                title="Lê Memória STM (Redis)"
              >
                STM
              </v-chip>
              <v-chip
                v-if="data.config?.load_mtm !== false && data.config?.load_mtm !== undefined"
                size="x-small"
                variant="tonal"
                color="indigo"
                density="compact"
                title="Lê Memória MTM (Postgres)"
              >
                MTM
              </v-chip>
              <v-chip
                v-if="data.config?.save_to_memory !== false && data.config?.save_to_memory !== undefined"
                size="x-small"
                variant="tonal"
                color="success"
                density="compact"
                title="Grava resposta na Memória (Chat)"
              >
                💾 Salva
              </v-chip>
            </div>
          </div>
        </div>

        <!-- Workflow Block Details -->
        <div v-else-if="data.type === 'workflow' || data.type === 'sub_workflow'" class="d-flex flex-column ga-1">
          <div class="d-flex align-center ga-1 text-caption text-medium-emphasis">
            <v-icon size="14" color="blue">mdi-sitemap</v-icon>
            <span class="text-truncate font-weight-medium text-blue" style="max-width: 160px;">
              {{ data.config?.workflow_name || 'Selecione um workflow...' }}
            </span>
          </div>
          <div v-if="data.config?.output_key" class="d-flex align-center ga-1 mt-1">
            <v-chip size="x-small" color="blue-darken-1" variant="tonal" density="compact">
              ${{ data.config?.output_key }}
            </v-chip>
            <span v-if="data.config?.inject_into_prompt !== false" class="text-caption text-success font-weight-bold" style="font-size: 9px !important;">
              ● Injetar no Prompt
            </span>
          </div>
        </div>

        <!-- Router / Supervisor with dynamic routes list -->
        <div v-else-if="data.type === 'router' || data.type === 'supervisor'">
          <div class="d-flex align-center ga-1 flex-wrap mb-1">
            <v-chip v-if="data.config?.model" size="x-small" variant="outlined" color="purple" density="compact">
              {{ data.config.model }}
            </v-chip>
            <v-chip
              v-if="data.config?.context_mapping && Object.keys(data.config.context_mapping).length"
              size="x-small"
              variant="tonal"
              color="cyan"
              density="compact"
              title="Schema de Payload configurado"
            >
              <v-icon start size="10">mdi-code-json</v-icon>Schema
            </v-chip>
            <v-chip
              v-if="data.config?.load_stm !== false && data.config?.load_stm !== undefined"
              size="x-small"
              variant="tonal"
              color="teal"
              density="compact"
              title="Lê Memória STM (Redis)"
            >
              STM
            </v-chip>
            <v-chip
              v-if="data.config?.load_mtm !== false && data.config?.load_mtm !== undefined"
              size="x-small"
              variant="tonal"
              color="indigo"
              density="compact"
              title="Lê Memória MTM (Postgres)"
            >
              MTM
            </v-chip>
          </div>
          <div v-if="routesList.length > 0" class="router-routes-container mt-1">
            <div class="text-caption text-medium-emphasis font-weight-bold mb-1" style="font-size: 10px !important;">
              ROTAS DE SAÍDA (LLM):
            </div>
            <div
              v-for="(route, idx) in routesList"
              :key="idx"
              class="route-item-badge d-flex align-center justify-space-between px-2 py-1 mb-1 rounded"
              :style="{ backgroundColor: 'rgba(139, 92, 246, 0.15)', borderLeft: '3px solid #8B5CF6' }"
            >
              <span class="text-caption font-weight-medium text-truncate" style="font-size: 10px !important; max-width: 130px;" :title="route.description">
                {{ idx + 1 }}. {{ route.name || ('Rota ' + (idx + 1)) }}
              </span>
              <span class="text-caption text-medium-emphasis" style="font-size: 9px !important;">#{{ route.id || ('route_' + idx) }}</span>
            </div>
            <!-- Fallback Outro -->
            <div
              class="route-item-badge d-flex align-center justify-space-between px-2 py-1 rounded"
              :style="{ backgroundColor: 'rgba(239, 68, 68, 0.15)', borderLeft: '3px solid #EF4444' }"
            >
              <span class="text-caption font-weight-medium text-error" style="font-size: 10px !important;">
                ● Outro (Fallback)
              </span>
              <span class="text-caption text-error" style="font-size: 9px !important;">#default</span>
            </div>
          </div>
          <div v-else class="text-caption text-medium-emphasis">
            <span>Roteamento inteligente via LLM</span>
          </div>
        </div>

        <!-- Parallel Fan-Out -->
        <div v-else-if="data.type === 'parallel'" class="text-caption text-medium-emphasis">
          <v-icon size="14" color="cyan" class="mr-1">mdi-call-split</v-icon>
          <span>Dispara múltiplos caminhos</span>
        </div>

        <!-- Synthesizer Fan-In -->
        <div v-else-if="data.type === 'synthesizer'" class="text-caption text-medium-emphasis">
          <div class="d-flex align-center ga-1 flex-wrap mb-1">
            <v-icon size="14" color="pink">mdi-call-merge</v-icon>
            <span class="font-weight-medium text-pink">Sintetizador</span>
            <v-chip v-if="data.config?.model" size="x-small" variant="outlined" color="pink" density="compact">
              {{ data.config.model }}
            </v-chip>
            <v-chip
              v-if="data.config?.context_mapping && Object.keys(data.config.context_mapping).length"
              size="x-small"
              variant="tonal"
              color="cyan"
              density="compact"
            >
              <v-icon start size="10">mdi-code-json</v-icon>Schema
            </v-chip>
            <v-chip
              v-if="data.config?.load_stm"
              size="x-small"
              variant="tonal"
              color="teal"
              density="compact"
            >
              STM
            </v-chip>
            <v-chip
              v-if="data.config?.load_mtm"
              size="x-small"
              variant="tonal"
              color="indigo"
              density="compact"
            >
              MTM
            </v-chip>
            <v-chip
              v-if="data.config?.save_to_memory !== false && data.config?.save_to_memory !== undefined"
              size="x-small"
              variant="tonal"
              color="success"
              density="compact"
            >
              💾 Salva
            </v-chip>
          </div>
          <span>Consolida respostas paralelas</span>
        </div>

        <!-- Condition / Decision -->
        <div v-else-if="data.type === 'condition' || data.type === 'decision'" class="text-caption text-medium-emphasis">
          <div class="d-flex align-center ga-1 flex-wrap mb-1">
            <span>Modo: <strong>{{ data.config?.mode || 'LLM' }}</strong></span>
            <v-chip v-if="data.config?.model && (!data.config?.mode || data.config?.mode === 'llm')" size="x-small" variant="outlined" color="amber" density="compact">
              {{ data.config.model }}
            </v-chip>
            <v-chip
              v-if="data.config?.context_mapping && Object.keys(data.config.context_mapping).length"
              size="x-small"
              variant="tonal"
              color="cyan"
              density="compact"
            >
              <v-icon start size="10">mdi-code-json</v-icon>Schema
            </v-chip>
          </div>
        </div>

        <!-- Judge / Curator / Verifier (Loop) -->
        <div v-else-if="data.type === 'judge' || data.type === 'curator' || data.type === 'verifier' || data.type === 'guardrail'" class="text-caption text-medium-emphasis">
          <div class="d-flex align-center ga-1 mb-1 flex-wrap">
            <v-icon size="14" color="amber-darken-1">mdi-scale-balance</v-icon>
            <span class="font-weight-medium text-amber-lighten-1">Juiz de Qualidade</span>
            <v-chip v-if="data.config?.model && data.config?.judge_mode !== 'agent'" size="x-small" variant="outlined" color="amber-darken-2" density="compact">
              {{ data.config.model }}
            </v-chip>
            <v-chip
              v-if="data.config?.context_mapping && Object.keys(data.config.context_mapping).length"
              size="x-small"
              variant="tonal"
              color="cyan"
              density="compact"
            >
              <v-icon start size="10">mdi-code-json</v-icon>Schema
            </v-chip>
          </div>
          <div class="d-flex align-center justify-space-between">
            <span>Max Loops: {{ data.config?.max_retries || 2 }}</span>
            <v-chip size="x-small" color="amber" variant="outlined" density="compact">
              {{ data.config?.judge_mode === 'agent' ? 'Agente Auditor' : 'LLM Custom' }}
            </v-chip>
          </div>
        </div>

        <!-- Tool / Action -->
        <div v-else-if="data.type === 'tool' || data.type === 'action'" class="text-caption text-medium-emphasis">
          <span>{{ data.config?.action_type || 'Ação MCP' }}</span>
        </div>
      </div>

      <!-- Handle indicators list for Decision / Verifier / Judge -->
      <div v-if="data.type === 'condition' || data.type === 'decision'" class="branch-indicators mt-2 d-flex justify-space-between px-1">
        <span class="handle-label text-success font-weight-bold">● Verdadeiro</span>
        <span class="handle-label text-error font-weight-bold">● Falso</span>
      </div>

      <div v-if="data.type === 'judge' || data.type === 'curator' || data.type === 'verifier' || data.type === 'guardrail'" class="branch-indicators mt-2 d-flex justify-space-between px-1">
        <span class="handle-label text-success font-weight-bold">● Aprovado (True)</span>
        <span class="handle-label text-amber-darken-1 font-weight-bold">● Refazer (False)</span>
      </div>
    </div>

    <!-- ═══ UNIVERSAL HANDLES ═══ -->

    <!-- 1. TOP HANDLE (Entrada Principal de Sequência) -->
    <Handle
      v-if="showTopTargetHandle"
      type="target"
      :position="Position.Top"
      id="in_top"
      class="node-handle handle-in-top"
      title="Entrada Principal"
    />

    <!-- 2. LATERAL HANDLES (Entrada Amarela para Retorno / Loops / Fora de Sequência) -->
    <Handle
      v-if="showLoopTargetHandle"
      type="target"
      :position="Position.Left"
      id="loop_in_left"
      class="node-handle handle-loop-in handle-loop-left"
      title="Entrada de Retorno / Loop (Esquerda)"
    />
    <Handle
      v-if="showLoopTargetHandle"
      type="target"
      :position="Position.Right"
      id="loop_in_right"
      class="node-handle handle-loop-in handle-loop-right"
      title="Entrada de Retorno / Loop (Direita)"
    />

    <!-- 3. BOTTOM HANDLE (Saída Principal de Sequência para nós padrão) -->
    <Handle
      v-if="showSingleBottomSourceHandle"
      type="source"
      :position="Position.Bottom"
      id="out_bottom"
      class="node-handle handle-out-bottom"
      title="Saída Principal"
    />

    <!-- 4. ROUTER / SUPERVISOR: Dynamic Bottom Route Handles -->
    <template v-if="isRouterNode">
      <!-- Dynamic Route Handles along bottom -->
      <Handle
        v-for="(route, idx) in routesList"
        :key="idx"
        type="source"
        :position="Position.Bottom"
        :id="route.id || `route_${idx}`"
        class="node-handle handle-branch handle-router-rule"
        :style="{ left: getRouterHandlePosition(idx, routesList.length + 1) }"
        :title="`Rota: ${route.name || ('Rota ' + (idx + 1))}`"
      />
      <!-- Fallback / Default Route Handle at bottom right -->
      <Handle
        type="source"
        :position="Position.Bottom"
        id="default"
        class="node-handle handle-branch handle-false"
        :style="{ left: getRouterHandlePosition(routesList.length, routesList.length + 1) }"
        title="Rota Padrão / Fallback (Outro)"
      />
    </template>

    <!-- 5. CONDITION / DECISION: True / False at Bottom -->
    <template v-if="data.type === 'condition' || data.type === 'decision'">
      <Handle
        type="source"
        :position="Position.Bottom"
        id="true"
        class="node-handle handle-branch handle-true"
        :style="{ left: '30%' }"
        title="Verdadeiro (True)"
      />
      <Handle
        type="source"
        :position="Position.Bottom"
        id="false"
        class="node-handle handle-branch handle-false"
        :style="{ left: '70%' }"
        title="Falso (False)"
      />
    </template>

    <!-- 6. JUDGE / CURATOR / VERIFIER / GUARDRAIL: Approved (Bottom) / Retry (Bottom/Lateral) -->
    <template v-if="data.type === 'judge' || data.type === 'curator' || data.type === 'verifier' || data.type === 'guardrail'">
      <Handle
        type="source"
        :position="Position.Bottom"
        id="approved"
        class="node-handle handle-branch handle-true"
        :style="{ left: '30%' }"
        title="Aprovado (True / Seguir)"
      />
      <Handle
        type="source"
        :position="Position.Bottom"
        id="retry"
        class="node-handle handle-branch handle-loop-out"
        :style="{ left: '70%' }"
        title="Reprovado (False / Loop de Correção)"
      />
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

const props = defineProps({
  id: String,
  label: String,
  data: { type: Object, default: () => ({}) },
})

defineEmits(['edit'])

const NODE_META = {
  start:        { icon: 'mdi-play-circle',       color: '#10B981', label: 'Início / Trigger' },
  agent:        { icon: 'mdi-robot',             color: '#3B82F6', label: 'Agente Especialista' },
  workflow:     { icon: 'mdi-sitemap',           color: '#2563EB', label: 'Workflow (Dados)' },
  sub_workflow: { icon: 'mdi-sitemap',           color: '#2563EB', label: 'Workflow (Dados)' },
  router:       { icon: 'mdi-source-branch',     color: '#8B5CF6', label: 'Supervisor / Router' },
  supervisor:   { icon: 'mdi-account-supervisor', color: '#8B5CF6', label: 'Supervisor / Router' },
  parallel:     { icon: 'mdi-call-split',        color: '#06B6D4', label: 'Fan-Out Paralelo' },
  synthesizer:  { icon: 'mdi-call-merge',        color: '#EC4899', label: 'Sintetizador Fan-In' },
  condition:    { icon: 'mdi-help-rhombus',      color: '#F59E0B', label: 'Decisão / Condição' },
  decision:     { icon: 'mdi-help-rhombus',      color: '#F59E0B', label: 'Decisão / Condição' },
  judge:        { icon: 'mdi-scale-balance',      color: '#EAB308', label: 'Juiz / Curador' },
  curator:      { icon: 'mdi-shield-check',      color: '#EAB308', label: 'Juiz / Curador' },
  verifier:     { icon: 'mdi-shield-check',      color: '#EAB308', label: 'Verificador (Loop)' },
  guardrail:    { icon: 'mdi-shield-check',      color: '#EAB308', label: 'Verificador (Loop)' },
  tool:         { icon: 'mdi-tools',             color: '#14B8A6', label: 'Ferramenta / Ação' },
  action:       { icon: 'mdi-tools',             color: '#14B8A6', label: 'Ferramenta / Ação' },
  end:          { icon: 'mdi-stop-circle',       color: '#64748B', label: 'Fim / Resposta' },
}

const meta = computed(() => NODE_META[props.data.type] || { icon: 'mdi-cube-outline', color: '#94A3B8', label: 'Bloco' })
const nodeIcon = computed(() => meta.value.icon)
const nodeColor = computed(() => meta.value.color)

const isInlineAgent = computed(() => {
  const cfg = props.data.config || {}
  return cfg.agent_mode === 'inline' || !!cfg.inline_agent
})

const isRouterNode = computed(() => {
  return props.data.type === 'router' || props.data.type === 'supervisor'
})

const routesList = computed(() => {
  return props.data.config?.routes || []
})

const showTopTargetHandle = computed(() => props.data.type !== 'start')
const showLoopTargetHandle = computed(() => props.data.type !== 'start')

const showSingleBottomSourceHandle = computed(() => {
  const t = props.data.type
  return t !== 'end' && t !== 'condition' && t !== 'decision' && t !== 'verifier' && t !== 'guardrail' && t !== 'router' && t !== 'supervisor'
})

const statusColor = computed(() => {
  switch (props.data._status) {
    case 'running': return 'info'
    case 'success': return 'success'
    case 'error': return 'error'
    default: return 'grey'
  }
})

function getRouterHandlePosition(index, total) {
  if (total <= 1) return '50%'
  const step = 100 / (total + 1)
  return `${Math.round(step * (index + 1))}%`
}
</script>

<style scoped>
.agent-graph-node {
  min-width: 210px;
  max-width: 260px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(22, 27, 46, 0.95);
  backdrop-filter: blur(12px);
  position: relative;
  overflow: visible;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
  transition: all 0.2s ease-in-out;
  cursor: pointer;
}

.agent-graph-node:hover {
  border-color: rgba(255, 255, 255, 0.35);
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.6);
  transform: translateY(-2px);
}

.node-accent-bar {
  height: 4px;
  width: 100%;
  border-top-left-radius: 12px;
  border-top-right-radius: 12px;
}

.node-icon-wrapper {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.node-title {
  font-size: 13px;
  color: #F3F4F6;
  line-height: 1.2;
}

.node-badge {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.handle-label {
  font-size: 9px;
  line-height: 14px;
}

/* Custom Vue Flow Handles */
.node-handle {
  width: 12px !important;
  height: 12px !important;
  border: 2px solid #1E293B !important;
  border-radius: 50% !important;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  z-index: 10 !important;
}

.node-handle:hover {
  transform: scale(1.4);
}

/* 1. Entrada Topo */
.handle-in-top {
  background: #10B981 !important;
  top: -6px !important;
}

/* 2. Saída Base */
.handle-out-bottom {
  background: #3B82F6 !important;
  bottom: -6px !important;
}

/* 3. Entrada Lateral Amarela (Retorno / Loop) */
.handle-loop-in {
  background: #F59E0B !important;
  box-shadow: 0 0 6px rgba(245, 158, 11, 0.6) !important;
}
.handle-loop-left {
  left: -6px !important;
}
.handle-loop-right {
  right: -6px !important;
}

.handle-loop-in:hover {
  box-shadow: 0 0 10px rgba(245, 158, 11, 0.9) !important;
}

/* 4. Saídas de Branching / Condições */
.handle-branch {
  bottom: -6px !important;
}

.handle-true {
  background: #10B981 !important;
}

.handle-false {
  background: #EF4444 !important;
}

.handle-loop-out {
  background: #F59E0B !important;
}

.handle-router-rule {
  background: #8B5CF6 !important;
}

.node-active-highlight {
  border-color: #3B82F6 !important;
  box-shadow: 0 0 20px rgba(59, 130, 246, 0.6) !important;
  animation: pulse-active 1.5s infinite alternate;
}

.node-error-highlight {
  border-color: #EF4444 !important;
  box-shadow: 0 0 20px rgba(239, 68, 68, 0.6) !important;
}

.node-executed {
  border-color: #6366F1 !important;
  box-shadow: 0 0 16px rgba(99, 102, 241, 0.75) !important;
  animation: pulse-executed 2s infinite alternate;
}

@keyframes pulse-active {
  from {
    box-shadow: 0 0 10px rgba(59, 130, 246, 0.4);
  }
  to {
    box-shadow: 0 0 25px rgba(59, 130, 246, 0.9);
  }
}

@keyframes pulse-executed {
  from {
    box-shadow: 0 0 8px rgba(99, 102, 241, 0.5);
  }
  to {
    box-shadow: 0 0 22px rgba(99, 102, 241, 0.95);
  }
}
</style>
