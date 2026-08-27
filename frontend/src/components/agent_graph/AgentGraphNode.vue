<template>
  <div
    :class="[
      'agent-graph-node',
      `node-type-${data.type || 'agent'}`,
      { 'node-active-highlight': data?._isActive, 'node-error-highlight': data?._hasError }
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
          <div class="d-flex flex-column">
            <span class="node-title font-weight-bold text-truncate" style="max-width: 140px;">
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

      <!-- Node Subtitle / Agent details -->
      <div class="node-details mt-2">
        <!-- Specialist Agent info -->
        <div v-if="data.type === 'agent'" class="d-flex align-center ga-1 text-caption text-medium-emphasis">
          <v-icon size="14" color="grey">mdi-account-tie</v-icon>
          <span class="text-truncate" style="max-width: 160px;">{{ data.config?.agent_name || 'Selecione um agente...' }}</span>
        </div>

        <!-- Router info -->
        <div v-else-if="data.type === 'router' || data.type === 'supervisor'" class="text-caption text-medium-emphasis">
          <span>Decisão inteligente via LLM</span>
        </div>

        <!-- Parallel Fan-Out -->
        <div v-else-if="data.type === 'parallel'" class="text-caption text-medium-emphasis">
          <v-icon size="14" color="cyan" class="mr-1">mdi-call-split</v-icon>
          <span>Dispara múltiplos caminhos</span>
        </div>

        <!-- Synthesizer Fan-In -->
        <div v-else-if="data.type === 'synthesizer'" class="text-caption text-medium-emphasis">
          <v-icon size="14" color="purple" class="mr-1">mdi-call-merge</v-icon>
          <span>Consolida respostas</span>
        </div>

        <!-- Condition / Decision -->
        <div v-else-if="data.type === 'condition' || data.type === 'decision'" class="text-caption text-medium-emphasis">
          <span>Modo: {{ data.config?.mode || 'LLM' }}</span>
        </div>

        <!-- Verifier / Guardrail (Loop) -->
        <div v-else-if="data.type === 'verifier' || data.type === 'guardrail'" class="text-caption text-medium-emphasis">
          <v-icon size="14" color="amber" class="mr-1">mdi-refresh</v-icon>
          <span>Max Loops: {{ data.config?.max_retries || 2 }}</span>
        </div>

        <!-- Tool / Action -->
        <div v-else-if="data.type === 'tool' || data.type === 'action'" class="text-caption text-medium-emphasis">
          <span>{{ data.config?.action_type || 'Ação MCP' }}</span>
        </div>
      </div>

      <!-- Handle indicators list for Decision / Verifier -->
      <div v-if="data.type === 'condition' || data.type === 'decision'" class="branch-indicators mt-2 d-flex flex-column align-end">
        <span class="handle-label text-success font-weight-bold">● Verdadeiro (True)</span>
        <span class="handle-label text-error font-weight-bold">● Falso (False)</span>
      </div>

      <div v-if="data.type === 'verifier' || data.type === 'guardrail'" class="branch-indicators mt-2 d-flex flex-column align-end">
        <span class="handle-label text-success font-weight-bold">● Aprovado</span>
        <span class="handle-label text-amber-darken-1 font-weight-bold">● Loop Refazer</span>
      </div>
    </div>

    <!-- Incoming Handle (Left) -->
    <Handle
      v-if="showTargetHandle"
      type="target"
      :position="Position.Left"
      class="node-handle handle-in"
    />

    <!-- Outgoing Default Handle (Right) -->
    <Handle
      v-if="showSingleSourceHandle"
      type="source"
      :position="Position.Right"
      class="node-handle handle-out"
    />

    <!-- Condition Handles (True / False) -->
    <template v-if="data.type === 'condition' || data.type === 'decision'">
      <Handle
        type="source"
        :position="Position.Right"
        id="true"
        class="node-handle handle-branch handle-true"
        :style="{ top: '45%' }"
        title="Verdadeiro"
      />
      <Handle
        type="source"
        :position="Position.Right"
        id="false"
        class="node-handle handle-branch handle-false"
        :style="{ top: '75%' }"
        title="Falso"
      />
    </template>

    <!-- Verifier Handles (Approved / Retry Loop) -->
    <template v-if="data.type === 'verifier' || data.type === 'guardrail'">
      <Handle
        type="source"
        :position="Position.Right"
        id="approved"
        class="node-handle handle-branch handle-true"
        :style="{ top: '45%' }"
        title="Aprovado (Seguir)"
      />
      <Handle
        type="source"
        :position="Position.Right"
        id="retry"
        class="node-handle handle-branch handle-loop"
        :style="{ top: '75%' }"
        title="Reprovado (Loop de Correção)"
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
  router:       { icon: 'mdi-source-branch',     color: '#8B5CF6', label: 'Supervisor / Router' },
  supervisor:   { icon: 'mdi-account-supervisor', color: '#8B5CF6', label: 'Supervisor / Router' },
  parallel:     { icon: 'mdi-call-split',        color: '#06B6D4', label: 'Fan-Out Paralelo' },
  synthesizer:  { icon: 'mdi-call-merge',        color: '#EC4899', label: 'Sintetizador Fan-In' },
  condition:    { icon: 'mdi-help-rhombus',      color: '#F59E0B', label: 'Decisão / Condição' },
  decision:     { icon: 'mdi-help-rhombus',      color: '#F59E0B', label: 'Decisão / Condição' },
  verifier:     { icon: 'mdi-shield-check',      color: '#EAB308', label: 'Verificador (Loop)' },
  guardrail:    { icon: 'mdi-shield-check',      color: '#EAB308', label: 'Verificador (Loop)' },
  tool:         { icon: 'mdi-tools',             color: '#14B8A6', label: 'Ferramenta / Ação' },
  action:       { icon: 'mdi-tools',             color: '#14B8A6', label: 'Ferramenta / Ação' },
  end:          { icon: 'mdi-stop-circle',       color: '#64748B', label: 'Fim / Resposta' },
}

const meta = computed(() => NODE_META[props.data.type] || { icon: 'mdi-cube-outline', color: '#94A3B8', label: 'Bloco' })
const nodeIcon = computed(() => meta.value.icon)
const nodeColor = computed(() => meta.value.color)

const showTargetHandle = computed(() => props.data.type !== 'start')
const showSingleSourceHandle = computed(() => {
  const t = props.data.type
  return t !== 'end' && t !== 'condition' && t !== 'decision' && t !== 'verifier' && t !== 'guardrail'
})

const statusColor = computed(() => {
  switch (props.data._status) {
    case 'running': return 'info'
    case 'success': return 'success'
    case 'error': return 'error'
    default: return 'grey'
  }
})
</script>

<style scoped>
.agent-graph-node {
  min-width: 200px;
  max-width: 240px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(22, 27, 46, 0.95);
  backdrop-filter: blur(12px);
  position: relative;
  overflow: hidden;
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
}

.node-icon-wrapper {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
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
  width: 10px !important;
  height: 10px !important;
  background: #3B82F6 !important;
  border: 2px solid #1E293B !important;
  border-radius: 50% !important;
  transition: transform 0.15s ease;
}

.node-handle:hover {
  transform: scale(1.3);
}

.handle-in {
  background: #10B981 !important;
}

.handle-out {
  background: #3B82F6 !important;
}

.handle-true {
  background: #10B981 !important;
}

.handle-false {
  background: #EF4444 !important;
}

.handle-loop {
  background: #F59E0B !important;
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

@keyframes pulse-active {
  from {
    box-shadow: 0 0 10px rgba(59, 130, 246, 0.4);
  }
  to {
    box-shadow: 0 0 25px rgba(59, 130, 246, 0.9);
  }
}
</style>
