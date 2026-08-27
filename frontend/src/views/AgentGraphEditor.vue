<template>
  <div class="agent-graph-editor-page d-flex flex-column" style="height: calc(100vh - 64px)">
    <!-- Header Toolbar -->
    <v-toolbar color="surface" elevation="2" class="px-4" height="60">
      <v-btn icon @click="goBack" class="mr-2"><v-icon>mdi-arrow-left</v-icon></v-btn>
      <div class="d-flex align-center">
        <v-icon color="primary" class="mr-2">mdi-graphql</v-icon>
        <v-text-field
          v-if="editingName"
          v-model="graph.name"
          variant="outlined"
          density="compact"
          hide-details
          autofocus
          class="graph-name-input mr-2"
          style="max-width: 320px;"
          @keydown.enter="editingName = false"
          @blur="editingName = false"
        ></v-text-field>
        <h2 v-else class="text-h6 mb-0 cursor-pointer" @click="editingName = true" title="Clique para editar o nome">
          {{ graph.name || 'Carregando Grafo...' }}
          <v-icon size="14" class="ml-1 opacity-50">mdi-pencil</v-icon>
        </h2>
      </div>

      <v-spacer></v-spacer>

      <v-chip class="mr-3" :color="saveStatus.color" variant="flat" size="small">
        <v-icon start size="14">{{ saveStatus.icon }}</v-icon>{{ saveStatus.text }}
      </v-chip>

      <v-btn variant="tonal" class="mr-2" @click="showSettingsDialog = true" prepend-icon="mdi-cog">
        Configurações
      </v-btn>
      <v-btn variant="tonal" color="info" class="mr-2" @click="showTestDrawer = true" prepend-icon="mdi-play-circle">
        Testar Grafo
      </v-btn>
      <v-btn color="primary" @click="saveGraph" :loading="saving" prepend-icon="mdi-content-save">
        Salvar
      </v-btn>
    </v-toolbar>

    <!-- Main Workspace -->
    <div class="d-flex flex-grow-1 position-relative" style="overflow: hidden">
      <!-- Toolbox Sidebar -->
      <v-navigation-drawer permanent location="left" width="260" color="surface-variant" elevation="4">
        <div class="pa-4 text-center border-b">
          <h3 class="text-subtitle-1 font-weight-bold mb-1 d-flex align-center justify-center ga-1">
            <v-icon size="20" color="primary">mdi-shape-plus</v-icon>Blocos de IA
          </h3>
          <p class="text-caption text-medium-emphasis mb-0">Arraste os blocos para o diagrama</p>
        </div>

        <v-list class="pa-2" density="compact">
          <div v-for="item in toolboxItems" :key="item.type"
            class="dnd-block-item ma-2 pa-3 rounded border d-flex align-center ga-3 cursor-grab"
            :draggable="true"
            @dragstart="onDragStart($event, item.type)"
          >
            <div class="dnd-icon-wrapper" :style="{ backgroundColor: item.color + '25', color: item.color }">
              <v-icon size="20">{{ item.icon }}</v-icon>
            </div>
            <div>
              <div class="text-subtitle-2 font-weight-bold" style="font-size: 12px !important; line-height: 1.2;">{{ item.label }}</div>
              <div class="text-caption text-medium-emphasis" style="font-size: 10px !important;">{{ item.desc }}</div>
            </div>
          </div>
        </v-list>
      </v-navigation-drawer>

      <!-- Vue Flow Canvas -->
      <div class="flex-grow-1 h-100 bg-background" @drop="onDrop" @dragover="onDragOver">
        <VueFlow
          v-model="elements"
          :node-types="nodeTypes"
          :default-edge-options="{ type: 'smoothstep', animated: true, style: { stroke: '#3B82F6', strokeWidth: 2 } }"
          fit-view-on-init
          class="dark-canvas"
          @node-click="onNodeClick"
          @pane-click="onPaneClick"
        >
          <Background pattern-color="#2D3748" :gap="18" />
          <Controls />
          <MiniMap />
        </VueFlow>
      </div>

      <!-- Properties Panel (Right Drawer) -->
      <AgentGraphPropertiesPanel
        v-if="selectedNode"
        :selected-node="selectedNode"
        @close="selectedNode = null"
        @delete="deleteSelectedNode"
      />
    </div>

    <!-- Settings Dialog -->
    <v-dialog v-model="showSettingsDialog" max-width="500">
      <v-card class="pa-4 bg-surface rounded-xl">
        <v-card-title class="font-weight-bold d-flex align-center ga-2">
          <v-icon color="primary">mdi-cog</v-icon>Configurações do Grafo
        </v-card-title>
        <v-card-text class="pt-2">
          <v-text-field
            v-model="graph.name"
            label="Nome do Grafo"
            variant="outlined"
            density="compact"
            class="mb-3"
          ></v-text-field>

          <v-textarea
            v-model="graph.description"
            label="Descrição do Grafo"
            variant="outlined"
            density="compact"
            rows="3"
            class="mb-3"
          ></v-textarea>

          <v-slider
            v-model="graph.recursion_limit"
            label="Limite de Recursão (Loops)"
            min="5"
            max="50"
            step="1"
            thumb-label="always"
            color="primary"
            class="mt-4"
          ></v-slider>

          <v-slider
            v-model="graph.timeout_seconds"
            label="Timeout Máximo (Segundos)"
            min="10"
            max="180"
            step="5"
            thumb-label="always"
            color="secondary"
            class="mt-4"
          ></v-slider>
        </v-card-text>
        <v-card-actions class="justify-end">
          <v-btn variant="flat" color="primary" @click="showSettingsDialog = false">Salvar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Live Test Drawer -->
    <v-navigation-drawer
      v-model="showTestDrawer"
      location="right"
      temporary
      width="450"
      class="bg-surface border-l"
    >
      <div class="pa-4 d-flex flex-column h-100">
        <div class="d-flex align-center justify-space-between mb-3 border-b pb-3">
          <div class="d-flex align-center ga-2">
            <v-icon color="info" size="24">mdi-play-circle</v-icon>
            <h3 class="text-subtitle-1 font-weight-bold mb-0">Testar Execução do Grafo</h3>
          </div>
          <v-btn icon="mdi-close" variant="text" size="small" @click="showTestDrawer = false"></v-btn>
        </div>

        <v-textarea
          v-model="testMessage"
          label="Mensagem do Usuário"
          variant="outlined"
          density="compact"
          rows="3"
          placeholder="Ex: Como está a saúde financeira e de membros da minha igreja?"
          class="mb-3"
        ></v-textarea>

        <v-btn
          color="primary"
          block
          size="large"
          prepend-icon="mdi-lightning-bolt"
          :loading="runningTest"
          @click="runGraphTest"
          class="mb-4"
        >
          Executar Grafo
        </v-btn>

        <!-- Test Result Section -->
        <div v-if="testResult" class="flex-grow-1 overflow-y-auto">
          <!-- Status Banner -->
          <v-alert
            :type="testResult.status === 'success' ? 'success' : 'error'"
            variant="tonal"
            density="compact"
            class="mb-3"
          >
            <div class="d-flex align-center justify-space-between">
              <span>Status: <strong>{{ testResult.status }}</strong></span>
              <span>Tempo Total: <strong>{{ testResult.total_duration_ms }}ms</strong></span>
            </div>
          </v-alert>

          <!-- Steps Trace Timeline -->
          <h4 class="text-subtitle-2 font-weight-bold mb-2">Trilha de Execução dos Nós</h4>
          <v-timeline density="compact" side="end" class="mb-4">
            <v-timeline-item
              v-for="(step, idx) in testResult.steps"
              :key="idx"
              :dot-color="step.status === 'success' ? 'primary' : 'error'"
              size="x-small"
            >
              <div class="d-flex flex-column ga-1">
                <div class="d-flex align-center justify-space-between">
                  <span class="text-caption font-weight-bold">{{ step.node_label }} ({{ step.node_type }})</span>
                  <span class="text-caption text-medium-emphasis">{{ step.duration_ms }}ms</span>
                </div>
                <div class="text-caption text-medium-emphasis pa-2 rounded bg-surface-variant font-mono" style="font-size: 11px !important;">
                  {{ typeof step.output_data === 'object' ? JSON.stringify(step.output_data) : step.output_data }}
                </div>
              </div>
            </v-timeline-item>
          </v-timeline>

          <!-- Final Output -->
          <h4 class="text-subtitle-2 font-weight-bold mb-1">Resposta Final</h4>
          <v-card class="pa-3 bg-surface-variant rounded-lg border">
            <div class="text-body-2" style="white-space: pre-wrap;">{{ testResult.final_output }}</div>
          </v-card>
        </div>
      </div>
    </v-navigation-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, markRaw } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import axios from '@/plugins/axios'

import AgentGraphNode from '@/components/agent_graph/AgentGraphNode.vue'
import AgentGraphPropertiesPanel from '@/components/agent_graph/AgentGraphPropertiesPanel.vue'

const route = useRoute()
const router = useRouter()
const graphId = route.params.id

const nodeTypes = {
  agentGraphNode: markRaw(AgentGraphNode),
}

const graph = reactive({
  id: '',
  name: '',
  description: '',
  is_active: true,
  recursion_limit: 25,
  timeout_seconds: 60,
  definition: { nodes: [], edges: [] }
})

const elements = ref([])
const editingName = ref(false)
const saving = ref(false)
const saveStatus = reactive({ color: 'grey', icon: 'mdi-cloud-outline', text: 'Não salvo' })
const showSettingsDialog = ref(false)
const selectedNode = ref(null)

const showTestDrawer = ref(false)
const testMessage = ref('')
const runningTest = ref(false)
const testResult = ref(null)

const { addNodes, project, getNodes, getEdges, removeNodes } = useVueFlow()

const toolboxItems = [
  { type: 'start', label: 'Início', icon: 'mdi-play-circle', color: '#10B981', desc: 'Entrada da mensagem' },
  { type: 'agent', label: 'Especialista', icon: 'mdi-robot', color: '#3B82F6', desc: 'Agente especialista' },
  { type: 'router', label: 'Supervisor', icon: 'mdi-source-branch', color: '#8B5CF6', desc: 'Roteador inteligente' },
  { type: 'parallel', label: 'Fan-Out Paralelo', icon: 'mdi-call-split', color: '#06B6D4', desc: 'Disparo concorrente' },
  { type: 'synthesizer', label: 'Sintetizador', icon: 'mdi-call-merge', color: '#EC4899', desc: 'Consolida respostas' },
  { type: 'condition', label: 'Decisão / Se', icon: 'mdi-help-rhombus', color: '#F59E0B', desc: 'Regra de desvio' },
  { type: 'verifier', label: 'Verificador Loop', icon: 'mdi-shield-check', color: '#EAB308', desc: 'Validação & Auto-correção' },
  { type: 'tool', label: 'Ação / MCP', icon: 'mdi-tools', color: '#14B8A6', desc: 'Chamada de ferramenta' },
  { type: 'end', label: 'Fim / Resposta', icon: 'mdi-stop-circle', color: '#64748B', desc: 'Saída final' },
]

const loadGraph = async () => {
  try {
    const res = await axios.get(`/agent-graphs/${graphId}`)
    const data = res.data
    graph.id = data.id
    graph.name = data.name
    graph.description = data.description
    graph.is_active = data.is_active
    graph.recursion_limit = data.recursion_limit || 25
    graph.timeout_seconds = data.timeout_seconds || 60
    graph.definition = data.definition || { nodes: [], edges: [] }

    // Hydrate Vue Flow elements
    const rawNodes = (graph.definition.nodes || []).map(n => ({
      ...n,
      type: 'agentGraphNode',
      data: { ...n.data }
    }))
    const rawEdges = graph.definition.edges || []

    // If empty graph, add Start and Agent by default
    if (rawNodes.length === 0) {
      const defaultStart = {
        id: 'start-1',
        type: 'agentGraphNode',
        position: { x: 100, y: 200 },
        data: { type: 'start', label: 'Início', config: {} }
      }
      const defaultAgent = {
        id: 'agent-1',
        type: 'agentGraphNode',
        position: { x: 380, y: 200 },
        data: { type: 'agent', label: 'Agente Especialista', config: {} }
      }
      elements.value = [
        defaultStart,
        defaultAgent,
        { id: 'e-start-agent', source: 'start-1', target: 'agent-1', type: 'smoothstep' }
      ]
    } else {
      elements.value = [...rawNodes, ...rawEdges]
    }
    saveStatus.color = 'success'
    saveStatus.icon = 'mdi-cloud-check'
    saveStatus.text = 'Sincronizado'
  } catch (e) {
    console.error('Erro ao carregar grafo:', e)
  }
}

const saveGraph = async () => {
  saving.value = true
  saveStatus.color = 'warning'
  saveStatus.icon = 'mdi-cloud-sync'
  saveStatus.text = 'Salvando...'
  try {
    const nodes = getNodes.value
    const edges = getEdges.value

    const payload = {
      name: graph.name,
      description: graph.description,
      is_active: graph.is_active,
      recursion_limit: graph.recursion_limit,
      timeout_seconds: graph.timeout_seconds,
      definition: { nodes, edges }
    }

    await axios.put(`/agent-graphs/${graphId}`, payload)
    saveStatus.color = 'success'
    saveStatus.icon = 'mdi-cloud-check'
    saveStatus.text = 'Salvo'
  } catch (e) {
    console.error('Erro ao salvar grafo:', e)
    saveStatus.color = 'error'
    saveStatus.icon = 'mdi-cloud-alert'
    saveStatus.text = 'Erro ao salvar'
  } finally {
    saving.value = false
  }
}

const onDragStart = (event, nodeType) => {
  if (event.dataTransfer) {
    event.dataTransfer.setData('application/vueflow-type', nodeType)
    event.dataTransfer.effectAllowed = 'move'
  }
}

const onDragOver = (event) => {
  event.preventDefault()
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'move'
  }
}

const onDrop = (event) => {
  const type = event.dataTransfer?.getData('application/vueflow-type')
  if (!type) return

  const position = project({
    x: event.clientX - 260,
    y: event.clientY - 60
  })

  const itemMeta = toolboxItems.find(i => i.type === type)
  const newNode = {
    id: `${type}-${Date.now()}`,
    type: 'agentGraphNode',
    position,
    data: {
      type,
      label: itemMeta?.label || type,
      config: {}
    }
  }

  addNodes([newNode])
}

const onNodeClick = ({ node }) => {
  selectedNode.value = node
}

const onPaneClick = () => {
  selectedNode.value = null
}

const deleteSelectedNode = (nodeId) => {
  removeNodes([nodeId])
  selectedNode.value = null
}

const runGraphTest = async () => {
  if (!testMessage.value.trim()) return
  runningTest.value = true
  testResult.value = null

  try {
    // Save first to ensure server has latest topology
    await saveGraph()

    const res = await axios.post(`/agent-graphs/${graphId}/test`, {
      message: testMessage.value
    })
    testResult.value = res.data
  } catch (e) {
    console.error('Erro ao testar grafo:', e)
    testResult.value = {
      status: 'error',
      final_output: 'Erro ao executar teste do grafo.',
      steps: [],
      total_duration_ms: 0
    }
  } finally {
    runningTest.value = false
  }
}

const goBack = () => {
  router.push('/agent-graphs')
}

onMounted(() => {
  loadGraph()
})
</script>

<style scoped>
.dnd-block-item {
  background: rgba(30, 41, 59, 0.7);
  border-color: rgba(255, 255, 255, 0.1) !important;
  transition: all 0.15s ease;
}

.dnd-block-item:hover {
  background: rgba(51, 65, 85, 0.9);
  border-color: rgba(255, 255, 255, 0.3) !important;
  transform: scale(1.02);
}

.dnd-icon-wrapper {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.cursor-grab {
  cursor: grab;
}

.dark-canvas {
  background-color: #0d111c;
}
</style>
