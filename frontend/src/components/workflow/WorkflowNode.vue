<template>
  <div :class="['workflow-node', `node-${data.type || 'default'}`]" @dblclick="$emit('edit', id)">
    <div class="node-header">
      <v-icon :color="nodeColor" size="18">{{ nodeIcon }}</v-icon>
      <span class="node-label">{{ label || data.label || 'Bloco' }}</span>
      <v-chip v-if="data._status" :color="statusColor" size="x-small" variant="flat" class="ml-1">
        {{ data._status }}
      </v-chip>
    </div>
    <div class="node-body" v-if="subtitle">
      <span class="node-subtitle">{{ subtitle }}</span>
    </div>
    <Handle v-if="showTargetHandle" type="target" :position="Position.Left" class="handle-in" />
    <Handle v-if="showSourceHandle" type="source" :position="Position.Right" class="handle-out" />
    <!-- IF/Router: extra handles for branching -->
    <Handle
      v-if="data.type === 'if'"
      type="source"
      :position="Position.Right"
      id="true"
      class="handle-branch handle-true"
      :style="{ top: '35%' }"
    />
    <Handle
      v-if="data.type === 'if'"
      type="source"
      :position="Position.Right"
      id="false"
      class="handle-branch handle-false"
      :style="{ top: '65%' }"
    />
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

const BLOCK_META = {
  trigger:      { icon: 'mdi-lightning-bolt',    color: '#F59E0B', label: 'Gatilho' },
  http_request: { icon: 'mdi-api',              color: '#3B82F6', label: 'HTTP' },
  if:           { icon: 'mdi-call-split',        color: '#8B5CF6', label: 'IF' },
  router:       { icon: 'mdi-source-branch',     color: '#8B5CF6', label: 'Router' },
  filter:       { icon: 'mdi-filter-variant',    color: '#06B6D4', label: 'Filter' },
  agent:        { icon: 'mdi-robot',             color: '#10B981', label: 'Agente' },
  transform:    { icon: 'mdi-swap-horizontal',   color: '#F97316', label: 'Transform' },
  delay:        { icon: 'mdi-timer-sand',        color: '#6B7280', label: 'Delay' },
}

const meta = computed(() => BLOCK_META[props.data.type] || { icon: 'mdi-help-circle', color: '#9CA3AF', label: 'Bloco' })
const nodeIcon = computed(() => meta.value.icon)
const nodeColor = computed(() => meta.value.color)

const subtitle = computed(() => {
  const cfg = props.data.config || {}
  switch (props.data.type) {
    case 'http_request':
      return cfg.method ? `${cfg.method} ${(cfg.url || '').substring(0, 40)}...` : ''
    case 'agent':
      return cfg.agent_id ? 'Agente vinculado' : 'Sem agente'
    case 'if':
      return cfg.operator ? `${cfg.operator}` : 'Condição'
    case 'delay':
      return cfg.delay_ms ? `${cfg.delay_ms}ms` : ''
    case 'trigger':
      return cfg.trigger_type || 'webhook'
    default:
      return ''
  }
})

const showTargetHandle = computed(() => props.data.type !== 'trigger')
const showSourceHandle = computed(() => props.data.type !== 'if') // IF uses branch handles

const statusColor = computed(() => {
  switch (props.data._status) {
    case 'running': return 'blue'
    case 'success': return 'success'
    case 'failed': return 'error'
    default: return 'grey'
  }
})
</script>

<style scoped>
.workflow-node {
  min-width: 180px;
  border-radius: 12px;
  border: 2px solid rgba(255,255,255,0.15);
  background: rgba(30, 30, 40, 0.95);
  backdrop-filter: blur(10px);
  transition: all 0.2s ease;
  cursor: pointer;
  box-shadow: 0 4px 20px rgba(0,0,0,0.3);
}
.workflow-node:hover {
  border-color: rgba(255,255,255,0.35);
  box-shadow: 0 6px 28px rgba(0,0,0,0.5);
  transform: translateY(-1px);
}

.node-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  font-weight: 600;
  font-size: 13px;
  color: #E5E7EB;
}
.node-body {
  padding: 0 14px 10px;
}
.node-subtitle {
  font-size: 11px;
  color: rgba(255,255,255,0.5);
  font-family: 'JetBrains Mono', monospace;
  word-break: break-all;
}

/* Type-specific border accents */
.node-trigger      { border-color: #F59E0B40; }
.node-http_request  { border-color: #3B82F640; }
.node-if            { border-color: #8B5CF640; }
.node-router        { border-color: #8B5CF640; }
.node-filter        { border-color: #06B6D440; }
.node-agent         { border-color: #10B98140; }
.node-transform     { border-color: #F9731640; }
.node-delay         { border-color: #6B728040; }

/* Handles */
.handle-in, .handle-out {
  width: 10px !important;
  height: 10px !important;
  background: #6366F1 !important;
  border: 2px solid #1E1E2E !important;
  border-radius: 50% !important;
}
.handle-branch {
  width: 10px !important;
  height: 10px !important;
  border: 2px solid #1E1E2E !important;
  border-radius: 50% !important;
}
.handle-true {
  background: #10B981 !important;
}
.handle-false {
  background: #EF4444 !important;
}

/* Execution status indicators */
.workflow-node[data-status="running"] {
  border-color: #3B82F6;
  animation: pulse-border 1.5s ease-in-out infinite;
}
.workflow-node[data-status="success"] {
  border-color: #10B981;
}
.workflow-node[data-status="failed"] {
  border-color: #EF4444;
}

@keyframes pulse-border {
  0%, 100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.5); }
  50% { box-shadow: 0 0 0 8px rgba(59, 130, 246, 0); }
}
</style>
