<template>
  <div class="workflow-editor-page d-flex flex-column" style="height: calc(100vh - 64px)">
    <!-- Header Toolbar -->
    <v-toolbar color="surface" elevation="2" class="px-4" height="60">
      <v-btn icon @click="goBack" class="mr-2"><v-icon>mdi-arrow-left</v-icon></v-btn>
      <div class="d-flex align-center">
        <v-icon color="primary" class="mr-2">mdi-sitemap</v-icon>
        <v-text-field
          v-if="editingName"
          v-model="workflow.name"
          variant="outlined"
          density="compact"
          hide-details
          autofocus
          class="workflow-name-input mr-2"
          style="max-width: 320px;"
          @keydown.enter="finishEditName"
          @blur="finishEditName"
        ></v-text-field>
        <h2 v-else class="text-h6 mb-0 workflow-name-display" @click="editingName = true" title="Clique para editar">
          {{ workflow.name || 'Carregando...' }}
          <v-icon size="14" class="ml-1 opacity-50">mdi-pencil</v-icon>
        </h2>
      </div>
      <v-spacer></v-spacer>
      <v-chip class="mr-3" :color="saveStatus.color" variant="flat" size="small">
        <v-icon start size="14">{{ saveStatus.icon }}</v-icon>{{ saveStatus.text }}
      </v-chip>
      <v-btn variant="tonal" class="mr-2" @click="openSettings" prepend-icon="mdi-cog">Configurações</v-btn>
      <v-btn variant="tonal" color="info" class="mr-2" @click="showTestDialog = true" prepend-icon="mdi-play-circle">Testar</v-btn>
      <v-btn color="primary" @click="saveDefinition" :loading="saving" prepend-icon="mdi-content-save">Salvar</v-btn>
    </v-toolbar>

    <!-- Main Editor Body -->
    <div class="d-flex flex-grow-1" style="overflow: hidden">
      <!-- Toolbox Sidebar -->
      <v-navigation-drawer permanent location="left" width="260" color="surface-variant" elevation="4">
        <div class="pa-4 text-center border-b">
          <h3 class="text-subtitle-1 font-weight-bold mb-1">
            <v-icon size="20" class="mr-1">mdi-toolbox-outline</v-icon>Blocos
          </h3>
          <p class="text-caption text-medium-emphasis">Arraste para o canvas</p>
        </div>
        <v-list class="pt-0" density="compact">
          <v-list-subheader class="font-weight-bold mt-2">Gatilhos</v-list-subheader>
          <div v-for="t in toolboxItems.filter(i => i.category === 'trigger')" :key="t.type"
            class="dndnode text-center ma-2 pa-3 cursor-grab rounded border" :draggable="true"
            @dragstart="onDragStart($event, t.type)">
            <v-icon :color="t.color" class="mb-1">{{ t.icon }}</v-icon>
            <div class="text-subtitle-2">{{ t.label }}</div>
          </div>
          <v-list-subheader class="font-weight-bold mt-2">Ações</v-list-subheader>
          <div v-for="t in toolboxItems.filter(i => i.category === 'action')" :key="t.type"
            class="dndnode text-center ma-2 pa-3 cursor-grab rounded border" :draggable="true"
            @dragstart="onDragStart($event, t.type)">
            <v-icon :color="t.color" class="mb-1">{{ t.icon }}</v-icon>
            <div class="text-subtitle-2">{{ t.label }}</div>
          </div>
          <v-list-subheader class="font-weight-bold mt-2">Lógica</v-list-subheader>
          <div v-for="t in toolboxItems.filter(i => i.category === 'logic')" :key="t.type"
            class="dndnode text-center ma-2 pa-3 cursor-grab rounded border" :draggable="true"
            @dragstart="onDragStart($event, t.type)">
            <v-icon :color="t.color" class="mb-1">{{ t.icon }}</v-icon>
            <div class="text-subtitle-2">{{ t.label }}</div>
          </div>
          <v-list-subheader class="font-weight-bold mt-2">Utilitários</v-list-subheader>
          <div v-for="t in toolboxItems.filter(i => i.category === 'utility')" :key="t.type"
            class="dndnode text-center ma-2 pa-3 cursor-grab rounded border" :draggable="true"
            @dragstart="onDragStart($event, t.type)">
            <v-icon :color="t.color" class="mb-1">{{ t.icon }}</v-icon>
            <div class="text-subtitle-2">{{ t.label }}</div>
          </div>
        </v-list>
      </v-navigation-drawer>

      <!-- Vue Flow Canvas -->
      <div class="vue-flow-container flex-grow-1" style="position: relative;" @drop="onDrop" @dragover.prevent>
        <VueFlow
          :nodes="nodes"
          :edges="edges"
          :node-types="nodeTypes"
          @pane-ready="onPaneReady"
          @node-click="onNodeClick"
          @pane-click="onPaneClick"
          @connect="onConnect"
          @nodes-change="onNodesChange"
          @edges-change="onEdgesChange"
          :delete-key-code="['Backspace', 'Delete']"
          :default-edge-options="{ type: 'smoothstep', animated: true, style: { stroke: '#6366F1', strokeWidth: 2 } }"
        >
          <Background pattern-color="#333" :gap="20" />
          <Controls />
          <MiniMap />
        </VueFlow>
      </div>

      <!-- Properties Panel -->
      <v-navigation-drawer :model-value="!!selectedBlock" location="right" width="520" color="surface" elevation="4" class="properties-drawer">
        <BlockPropertiesPanel
          v-if="selectedBlock"
          :block="selectedBlock"
          :agents="agentsList"
          :webhook-configs="webhooksList"
          :context-keys="availableContextKeys"
          @update="onBlockUpdate"
          @close="selectedBlock = null"
          @delete="deleteSelectedBlock"
          @duplicate="duplicateBlock"
        />
      </v-navigation-drawer>
    </div>

    <!-- Test Execution Dialog -->
    <v-dialog v-model="showTestDialog" max-width="750">
      <v-card>
        <v-card-title class="bg-primary text-white d-flex align-center">
          <v-icon class="mr-2">mdi-play-circle</v-icon>Testar Workflow
          <v-spacer></v-spacer>
          <v-btn icon variant="text" color="white" @click="showTestDialog = false"><v-icon>mdi-close</v-icon></v-btn>
        </v-card-title>
        <v-card-text class="pt-4">
          <v-textarea v-model="testPayloadJson" label="Payload de Teste (JSON)" variant="outlined" rows="8"
            placeholder='{"api_base": "https://...", "leader_id": "123", "auth_token": "..."}'
            class="monospace-field"></v-textarea>

          <!-- Status Banner -->
          <v-alert v-if="testResult" :type="testResult.status === 'completed' ? 'success' : 'error'" variant="tonal" class="mt-3">
            <div class="font-weight-bold mb-1">{{ testResult.status === 'completed' ? '✅ Sucesso' : '❌ Falha' }}</div>
            <div class="text-caption">{{ testResult.blocks_count }} blocos executados em {{ testResult.duration_ms }}ms</div>
            <div v-if="testResult.error" class="text-caption mt-1" style="color: #EF4444">{{ testResult.error }}</div>
          </v-alert>

          <!-- Tabs: Resultado Final vs Log Completo -->
          <v-tabs v-if="testResult && testResult.status === 'completed'" v-model="testResultTab" class="mt-4" color="primary" density="compact">
            <v-tab value="final">
              <v-icon start size="16">mdi-target</v-icon>
              Resultado Final
            </v-tab>
            <v-tab value="log">
              <v-icon start size="16">mdi-format-list-bulleted</v-icon>
              Log Completo
            </v-tab>
          </v-tabs>

          <v-window v-if="testResult && testResult.status === 'completed'" v-model="testResultTab" class="mt-3">
            <!-- Tab: Resultado Final (last block output only) -->
            <v-window-item value="final">
              <v-alert type="info" variant="tonal" density="compact" class="mb-3">
                <v-icon start size="14">mdi-information</v-icon>
                Este é o resultado que o agente/produção receberá — apenas a saída do último bloco executado.
              </v-alert>
              <div v-if="testResult.result" class="result-box pa-3 rounded">
                <pre class="text-body-2" style="white-space: pre-wrap; overflow: auto; max-height: 400px; margin: 0;">{{ JSON.stringify(testResult.result, null, 2) }}</pre>
              </div>
              <v-alert v-else type="warning" variant="tonal" density="compact">
                Nenhum resultado de saída gerado.
              </v-alert>
            </v-window-item>

            <!-- Tab: Log Completo (all blocks + full context) -->
            <v-window-item value="log">
              <v-expansion-panels v-if="testResult.blocks && testResult.blocks.length" variant="accordion">
                <v-expansion-panel v-for="(b, i) in testResult.blocks" :key="i">
                  <v-expansion-panel-title>
                    <v-icon :color="b.status === 'success' ? 'green' : 'red'" size="16" class="mr-2">
                      {{ b.status === 'success' ? 'mdi-check-circle' : 'mdi-close-circle' }}
                    </v-icon>
                    {{ b.label || b.block_id }} ({{ b.block_type }}) — {{ b.duration_ms }}ms
                  </v-expansion-panel-title>
                  <v-expansion-panel-text>
                    <pre class="text-caption" style="white-space: pre-wrap; max-height: 200px; overflow: auto">{{ JSON.stringify(b, null, 2) }}</pre>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>

              <!-- Full Context -->
              <v-expansion-panels class="mt-3">
                <v-expansion-panel>
                  <v-expansion-panel-title>
                    <v-icon size="16" class="mr-2">mdi-database</v-icon>
                    Contexto Completo (todos os blocos)
                  </v-expansion-panel-title>
                  <v-expansion-panel-text>
                    <pre class="text-caption" style="white-space: pre-wrap; max-height: 400px; overflow: auto">{{ JSON.stringify(testResult.context, null, 2) }}</pre>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
            </v-window-item>
          </v-window>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="showTestDialog = false">Fechar</v-btn>
          <v-btn color="primary" @click="runTest" :loading="testing" prepend-icon="mdi-play">Executar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Workflow Settings Dialog -->
    <v-dialog v-model="showSettingsDialog" max-width="600px">
      <v-card>
        <v-card-title class="bg-surface-variant d-flex align-center">
          <v-icon class="mr-2">mdi-cog</v-icon>
          Configurações do Workflow
        </v-card-title>
        <v-card-text class="pt-4">
          <v-alert
            type="info"
            variant="tonal"
            class="mb-4"
            text="Estas configurações definem como este workflow se comporta quando vinculado a um Agente."
          ></v-alert>

          <v-switch
            v-if="workflow.definition && workflow.definition.settings"
            v-model="workflow.definition.settings.auto_run"
            color="primary"
            label="Executar no Início do Agente (Auto-run / Pre-hook)"
            hint="Se ativado, quando o agente for acionado, este workflow será executado automaticamente ANTES do agente 'pensar', e o resultado será injetado no contexto dele."
            persistent-hint
            @change="markUnsaved"
          ></v-switch>
        </v-card-text>
        <v-card-actions class="pa-4 bg-surface-variant">
          <v-spacer></v-spacer>
          <v-btn color="primary" @click="showSettingsDialog = false">Fechar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, markRaw } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import axios from '@/plugins/axios'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import WorkflowNode from '@/components/workflow/WorkflowNode.vue'
import BlockPropertiesPanel from '@/components/workflow/BlockPropertiesPanel.vue'

const router = useRouter()
const route = useRoute()
const workflowId = route.params.id

const { project } = useVueFlow()
const vueFlowInstance = ref(null)

const workflow = ref({})
const nodes = ref([])
const edges = ref([])
const agentsList = ref([])
const webhooksList = ref([])
const saving = ref(false)
const selectedBlock = ref(null)
const saveStatus = ref({ text: 'Salvo', color: 'success', icon: 'mdi-check' })
const editingName = ref(false)
const showSettingsDialog = ref(false)
const showTestDialog = ref(false)
const testPayloadJson = ref('{\n  \n}')
const testResult = ref(null)
const testing = ref(false)
const testResultTab = ref('final')

let idCounter = 1

const nodeTypes = { workflow: markRaw(WorkflowNode) }

const toolboxItems = [
  { type: 'trigger', label: 'Webhook', icon: 'mdi-lightning-bolt', color: '#F59E0B', category: 'trigger' },
  { type: 'http_request', label: 'HTTP Request', icon: 'mdi-api', color: '#3B82F6', category: 'action' },
  { type: 'agent', label: 'Agente IA', icon: 'mdi-robot', color: '#10B981', category: 'action' },
  { type: 'if', label: 'IF (Condição)', icon: 'mdi-call-split', color: '#8B5CF6', category: 'logic' },
  { type: 'router', label: 'Router', icon: 'mdi-source-branch', color: '#8B5CF6', category: 'logic' },
  { type: 'filter', label: 'Filter', icon: 'mdi-filter-variant', color: '#06B6D4', category: 'logic' },
  { type: 'transform', label: 'Transform', icon: 'mdi-swap-horizontal', color: '#F97316', category: 'utility' },
  { type: 'delay', label: 'Delay', icon: 'mdi-timer-sand', color: '#6B7280', category: 'utility' },
]

const availableContextKeys = computed(() => {
  const keys = ['trigger']
  for (const node of nodes.value) {
    const outputKey = node.data?.config?.output_key || node.id
    if (outputKey && !keys.includes(outputKey)) keys.push(outputKey)
  }
  return keys
})

onMounted(async () => {
  await Promise.all([fetchAgents(), fetchWebhooks(), loadWorkflow()])
})

async function fetchAgents() {
  try { agentsList.value = (await axios.get('/agents')).data.agents || [] } catch {}
}
async function fetchWebhooks() {
  try { webhooksList.value = (await axios.get('/webhooks-config')).data.webhook_configs || [] } catch {}
}

async function loadWorkflow() {
  try {
    const res = await axios.get(`/workflows/${workflowId}`)
    workflow.value = res.data.workflow || res.data
    const def = workflow.value.definition || {}
    if (def.blocks && def.edges) {
      // v2 format
      nodes.value = def.blocks.map(b => ({
        id: b.id,
        type: 'workflow',
        position: b.position || { x: 0, y: 0 },
        label: b.label || b.type,
        data: { type: b.type, config: b.config || {}, label: b.label },
      }))
      edges.value = def.edges.map((e, i) => ({
        id: e.id || `e-${i}`,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle || e.label || null,
        label: e.label || '',
        type: 'smoothstep',
        animated: true,
        style: { stroke: e.label === 'true' ? '#10B981' : e.label === 'false' ? '#EF4444' : '#6366F1', strokeWidth: 2 },
      }))
      // Update counter
      for (const n of nodes.value) {
        const num = parseInt(n.id.split('_').pop())
        if (!isNaN(num) && num >= idCounter) idCounter = num + 1
      }
    } else if (def.elements) {
      // Legacy v1 format
      nodes.value = def.elements.filter(e => !e.source).map(e => ({
        id: e.id, type: 'workflow', position: e.position || { x: 0, y: 0 },
        label: e.label || '', data: e.data || {},
      }))
      edges.value = def.elements.filter(e => e.source).map(e => ({
        id: e.id, source: e.source, target: e.target, type: 'smoothstep', animated: true,
        style: { stroke: '#6366F1', strokeWidth: 2 },
      }))
    }
  } catch (e) { console.error("Failed to load workflow", e) }
}

const onPaneReady = (instance) => { vueFlowInstance.value = instance; instance.fitView() }
const onDragStart = (event, type) => {
  event.dataTransfer.setData('application/vueflow', type)
  event.dataTransfer.effectAllowed = 'move'
}

function onDrop(event) {
  event.preventDefault()
  const type = event.dataTransfer?.getData('application/vueflow')
  if (!type || !vueFlowInstance.value) return
  const position = project({ x: event.clientX - 260, y: event.clientY - 60 })
  const blockId = `block_${idCounter++}`
  const label = toolboxItems.find(t => t.type === type)?.label || type
  nodes.value = [...nodes.value, {
    id: blockId, type: 'workflow', position,
    label, data: { type, config: { output_key: blockId }, label },
  }]
  markUnsaved()
}

function onConnect(params) {
  const edgeId = `e-${params.source}-${params.target}-${params.sourceHandle || 'default'}`
  const label = params.sourceHandle || ''
  edges.value = [...edges.value, {
    id: edgeId, source: params.source, target: params.target,
    sourceHandle: params.sourceHandle, label,
    type: 'smoothstep', animated: true,
    style: { stroke: label === 'true' ? '#10B981' : label === 'false' ? '#EF4444' : '#6366F1', strokeWidth: 2 },
  }]
  markUnsaved()
}

function onNodesChange(changes) {
  for (const c of changes) {
    if (c.type === 'position' && c.position) {
      const node = nodes.value.find(n => n.id === c.id)
      if (node) { node.position = c.position; markUnsaved() }
    }
    if (c.type === 'remove') {
      nodes.value = nodes.value.filter(n => n.id !== c.id)
      edges.value = edges.value.filter(e => e.source !== c.id && e.target !== c.id)
      if (selectedBlock.value && selectedBlock.value.id === c.id) selectedBlock.value = null
      markUnsaved()
    }
  }
}
function onEdgesChange(changes) {
  for (const c of changes) {
    if (c.type === 'remove') {
      edges.value = edges.value.filter(e => e.id !== c.id)
      markUnsaved()
    }
  }
}

function onNodeClick({ node }) {
  selectedBlock.value = { id: node.id, ...node.data }
}
function onPaneClick() { selectedBlock.value = null }

function onBlockUpdate(block) {
  const node = nodes.value.find(n => n.id === block.id)
  if (node) {
    node.data = { ...block }
    node.label = block.label || node.label
  }
  markUnsaved()
}

function deleteSelectedBlock() {
  if (!selectedBlock.value) return
  const id = selectedBlock.value.id
  nodes.value = nodes.value.filter(n => n.id !== id)
  edges.value = edges.value.filter(e => e.source !== id && e.target !== id)
  selectedBlock.value = null
  markUnsaved()
}

function duplicateBlock() {
  if (!selectedBlock.value) return
  const sourceNode = nodes.value.find(n => n.id === selectedBlock.value.id)
  if (!sourceNode) return
  const newId = `block_${idCounter++}`
  const newNode = {
    id: newId,
    type: 'workflow',
    position: { x: sourceNode.position.x + 60, y: sourceNode.position.y + 80 },
    label: `${sourceNode.label || sourceNode.data.label || 'Bloco'} (cópia)`,
    data: {
      type: sourceNode.data.type,
      config: JSON.parse(JSON.stringify({ ...sourceNode.data.config, output_key: newId })),
      label: `${sourceNode.data.label || sourceNode.label || 'Bloco'} (cópia)`,
    },
  }
  nodes.value = [...nodes.value, newNode]
  selectedBlock.value = { id: newNode.id, ...newNode.data }
  markUnsaved()
}

function markUnsaved() { saveStatus.value = { text: 'Não Salvo', color: 'warning', icon: 'mdi-alert-circle' } }

function finishEditName() {
  editingName.value = false
  markUnsaved()
}

function openSettings() {
  if (!workflow.value.definition.settings) {
    workflow.value.definition.settings = { auto_run: false }
  }
  showSettingsDialog.value = true
}

async function saveDefinition() {
  try {
    saving.value = true
    const blocks = nodes.value.map(n => ({
      id: n.id, type: n.data.type, label: n.data.label || n.label,
      position: n.position, config: n.data.config || {},
    }))
    const edgesDef = edges.value.map(e => ({
      id: e.id, source: e.source, target: e.target,
      sourceHandle: e.sourceHandle || null, label: e.label || '',
    }))
    const definition = { 
        version: '2.0', 
        blocks, 
        edges: edgesDef, 
        variables: workflow.value.definition?.variables || {},
        settings: workflow.value.definition?.settings || { auto_run: false }
    }
    await axios.put(`/workflows/${workflowId}`, {
      name: workflow.value.name, description: workflow.value.description,
      is_active: workflow.value.is_active,
      definition
    })
    saveStatus.value = { text: 'Salvo', color: 'success', icon: 'mdi-check' }
  } catch (e) {
    console.error(e)
    saveStatus.value = { text: 'Erro ao Salvar', color: 'error', icon: 'mdi-close-circle' }
  } finally { saving.value = false }
}

async function runTest() {
  testing.value = true; testResult.value = null; testResultTab.value = 'final'
  try {
    await saveDefinition()
    let payload = {}
    try { payload = JSON.parse(testPayloadJson.value) } catch {}
    const res = await axios.post(`/workflows/${workflowId}/execute`, { trigger_data: payload })
    const exec = res.data
    testResult.value = {
      status: exec.status, duration_ms: exec.duration_ms,
      blocks_count: (exec.blocks_executed || []).length,
      blocks: exec.blocks_executed || [], error: exec.error_message,
      result: exec.result,
      context: exec.context || {},
    }
  } catch (e) {
    testResult.value = { status: 'failed', error: e.response?.data?.detail || e.message, blocks_count: 0, duration_ms: 0 }
  } finally { testing.value = false }
}

function goBack() { router.push('/workflows') }
</script>

<style scoped>
.workflow-editor-page { background-color: #0F0F17; }
.dndnode { border: 1px solid rgba(255,255,255,0.15); transition: all 0.2s ease; user-select: none; }
.dndnode:hover { background: rgba(255,255,255,0.05); border-color: rgba(255,255,255,0.4); transform: translateY(-2px); }
.properties-drawer { border-left: 1px solid rgba(255,255,255,0.1); }
.monospace-field :deep(textarea) { font-family: 'JetBrains Mono', monospace !important; font-size: 12px !important; }
.workflow-name-display { cursor: pointer; transition: opacity 0.2s; }
.workflow-name-display:hover { opacity: 0.75; }
.workflow-name-input :deep(.v-field) { font-size: 1.25rem; font-weight: bold; }
.result-box {
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(99, 102, 241, 0.3);
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}
.result-box pre { color: #A5F3FC; }
</style>
