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
        <h2 v-else class="text-h6 mb-0 cursor-pointer graph-name-display" @click="editingName = true" title="Clique para editar o nome">
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
      <v-btn variant="tonal" color="info" class="mr-2" @click="openTestChatDrawer" prepend-icon="mdi-chat-processing-outline">
        Testar Grafo (Chat)
      </v-btn>
      <v-btn color="primary" @click="saveGraph" :loading="saving" prepend-icon="mdi-content-save">
        Salvar
      </v-btn>
    </v-toolbar>

    <!-- Main Workspace -->
    <div class="d-flex flex-grow-1" style="overflow: hidden">
      <!-- Toolbox Sidebar -->
      <v-navigation-drawer permanent location="left" width="260" color="surface-variant" elevation="4">
        <div class="pa-4 text-center border-b">
          <h3 class="text-subtitle-1 font-weight-bold mb-1 d-flex align-center justify-center ga-1">
            <v-icon size="20" color="primary">mdi-shape-plus</v-icon>Blocos de IA
          </h3>
          <p class="text-caption text-medium-emphasis mb-0">Arraste para o canvas</p>
        </div>

        <v-list class="pt-0" density="compact">
          <v-list-subheader class="font-weight-bold mt-2">Agentes & Supervisores</v-list-subheader>
          <div
            v-for="t in toolboxItems.filter(i => i.category === 'agents')"
            :key="t.type"
            class="dndnode text-center ma-2 pa-3 cursor-grab rounded border"
            :draggable="true"
            @dragstart="onDragStart($event, t.type)"
          >
            <v-icon :color="t.color" class="mb-1">{{ t.icon }}</v-icon>
            <div class="text-subtitle-2">{{ t.label }}</div>
          </div>

          <v-list-subheader class="font-weight-bold mt-2">Automação & Workflows</v-list-subheader>
          <div
            v-for="t in toolboxItems.filter(i => i.category === 'workflows')"
            :key="t.type"
            class="dndnode text-center ma-2 pa-3 cursor-grab rounded border"
            :draggable="true"
            @dragstart="onDragStart($event, t.type)"
          >
            <v-icon :color="t.color" class="mb-1">{{ t.icon }}</v-icon>
            <div class="text-subtitle-2">{{ t.label }}</div>
          </div>

          <v-list-subheader class="font-weight-bold mt-2">Fluxo & Paralelismo</v-list-subheader>
          <div
            v-for="t in toolboxItems.filter(i => i.category === 'flow')"
            :key="t.type"
            class="dndnode text-center ma-2 pa-3 cursor-grab rounded border"
            :draggable="true"
            @dragstart="onDragStart($event, t.type)"
          >
            <v-icon :color="t.color" class="mb-1">{{ t.icon }}</v-icon>
            <div class="text-subtitle-2">{{ t.label }}</div>
          </div>

          <v-list-subheader class="font-weight-bold mt-2">Julgamento, Decisão & Loops</v-list-subheader>
          <div
            v-for="t in toolboxItems.filter(i => i.category === 'decision')"
            :key="t.type"
            class="dndnode text-center ma-2 pa-3 cursor-grab rounded border"
            :draggable="true"
            @dragstart="onDragStart($event, t.type)"
          >
            <v-icon :color="t.color" class="mb-1">{{ t.icon }}</v-icon>
            <div class="text-subtitle-2">{{ t.label }}</div>
          </div>

          <v-list-subheader class="font-weight-bold mt-2">Ações & Fim</v-list-subheader>
          <div
            v-for="t in toolboxItems.filter(i => i.category === 'actions')"
            :key="t.type"
            class="dndnode text-center ma-2 pa-3 cursor-grab rounded border"
            :draggable="true"
            @dragstart="onDragStart($event, t.type)"
          >
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
          @edge-click="onEdgeClick"
          @connect="onConnect"
          @nodes-change="onNodesChange"
          @edges-change="onEdgesChange"
          :delete-key-code="['Backspace', 'Delete']"
          :default-edge-options="{ type: 'smoothstep', animated: true, style: { stroke: '#3B82F6', strokeWidth: 2 } }"
          :pan-on-drag="[1]"
          :selection-on-drag="true"
          :selection-key-code="true"
          :pan-activation-key-code="'Space'"
        >
          <Background pattern-color="#2D3748" :gap="18" />
          <Controls />
          <MiniMap />
        </VueFlow>

        <!-- Floating Menu for Connection Line Style / Delete -->
        <div
          v-if="showEdgeMenu"
          class="floating-edge-menu pa-2 rounded border"
          :style="{
            position: 'fixed',
            top: `${edgeMenuPosition.y}px`,
            left: `${edgeMenuPosition.x}px`,
            zIndex: 9999,
            background: 'rgba(20, 20, 30, 0.98)',
            borderColor: 'rgba(255,255,255,0.15)',
            boxShadow: '0 8px 30px rgba(0,0,0,0.5)',
            backdropFilter: 'blur(10px)',
            minWidth: '220px'
          }"
        >
          <div class="d-flex align-center justify-space-between mb-2 px-1">
            <span class="text-caption font-weight-bold text-medium-emphasis" style="font-size: 9px !important; letter-spacing: 0.5px; color: #9CA3AF !important;">ESTILO DE CONEXÃO</span>
            <v-btn icon variant="text" size="x-small" @click="showEdgeMenu = false"><v-icon size="14">mdi-close</v-icon></v-btn>
          </div>
          <div class="d-flex flex-wrap px-1 mb-2" style="gap: 6px;">
            <div
              v-for="color in connectionColors"
              :key="color.value"
              class="color-dot cursor-pointer"
              :style="{
                backgroundColor: color.value,
                width: '20px',
                height: '20px',
                borderRadius: '50%',
                border: selectedEdge?.style?.stroke === color.value ? '2px solid white' : '1px solid rgba(255,255,255,0.2)',
                boxShadow: '0 2px 4px rgba(0,0,0,0.3)',
                transition: 'transform 0.1s'
              }"
              @click="setEdgeColor(color.value)"
              :title="color.name"
            ></div>
          </div>
          <v-divider class="my-2 border-opacity-25"></v-divider>
          <v-btn
            color="error"
            variant="text"
            block
            size="small"
            density="compact"
            prepend-icon="mdi-trash-can"
            @click="deleteSelectedEdge"
            class="justify-start"
          >
            Excluir Conexão
          </v-btn>
        </div>
      </div>

      <!-- Properties Drawer (Right) -->
      <v-navigation-drawer
        :model-value="!!selectedNode"
        location="right"
        width="340"
        color="surface"
        elevation="4"
        class="properties-drawer"
      >
        <AgentGraphPropertiesPanel
          v-if="selectedNode"
          :selected-node="selectedNode"
          @close="selectedNode = null"
          @delete="deleteSelectedNode"
        />
      </v-navigation-drawer>
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

    <!-- ═══ INTERACTIVE MULTI-TURN TEST CHAT DRAWER ═══ -->
    <v-navigation-drawer
      v-model="showTestDrawer"
      location="right"
      temporary
      width="580"
      class="bg-surface border-l test-chat-drawer"
    >
      <div class="d-flex flex-column h-100">
        <!-- Header -->
        <div class="pa-3 border-b d-flex align-center justify-space-between bg-surface-variant">
          <div class="d-flex align-center ga-2">
            <v-icon color="primary" size="22">mdi-chat-processing</v-icon>
            <div>
              <h3 class="text-subtitle-2 font-weight-bold mb-0">Chat de Teste do Grafo</h3>
              <span class="text-caption text-medium-emphasis" style="font-size: 10px !important;">
                Sessão: {{ testSessionId.slice(0, 8) }}...
              </span>
            </div>
          </div>
          <div class="d-flex align-center ga-1">
            <v-btn
              icon="mdi-code-json"
              variant="text"
              size="small"
              :color="showContextEditor ? 'primary' : 'default'"
              @click="showContextEditor = !showContextEditor"
              title="Parâmetros de Contexto (JSON)"
            ></v-btn>
            <v-btn
              icon="mdi-refresh"
              variant="text"
              size="small"
              color="warning"
              @click="resetChatSession"
              title="Reiniciar Conversa / Nova Sessão"
            ></v-btn>
            <v-btn icon="mdi-close" variant="text" size="small" @click="showTestDrawer = false"></v-btn>
          </div>
        </div>

        <!-- Collapsible Context Editor -->
        <v-expand-transition>
          <div v-if="showContextEditor" class="pa-3 border-b bg-surface">
            <div class="d-flex align-center justify-space-between mb-1">
              <span class="text-caption font-weight-bold text-medium-emphasis d-flex align-center ga-1">
                <v-icon size="14" color="primary">mdi-code-json</v-icon>
                Contexto / Parâmetros Iniciais (JSON)
              </span>
              <div class="d-flex align-center ga-1">
                <v-btn variant="text" size="x-small" density="compact" color="primary" @click="formatTestJson">
                  Formatar
                </v-btn>
                <v-btn variant="text" size="x-small" density="compact" color="secondary" @click="insertExampleJson">
                  Exemplo
                </v-btn>
              </div>
            </div>
            <v-textarea
              v-model="testPayloadJson"
              variant="outlined"
              density="compact"
              rows="4"
              placeholder='{\n  "church_name": "Igreja Central",\n  "user_name": "Fernando"\n}'
              class="monospace-field"
              hide-details
            ></v-textarea>
          </div>
        </v-expand-transition>

        <!-- Chat Messages Flow -->
        <div ref="chatContainerRef" class="chat-messages-container flex-grow-1 overflow-y-auto pa-4">
          <!-- Empty State -->
          <div v-if="chatMessages.length === 0" class="empty-chat text-center pa-6">
            <v-icon size="48" color="primary" class="mb-3 opacity-60">mdi-robot-outline</v-icon>
            <h4 class="text-subtitle-1 font-weight-bold mb-1">Pronto para Testar</h4>
            <p class="text-caption text-medium-emphasis mb-4">
              Envie uma mensagem abaixo para iniciar a execução do grafo e acompanhar em tempo real o caminho percorrido pelos agentes no canvas.
            </p>
            <div class="d-flex flex-column ga-2 max-w-sm mx-auto">
              <v-btn
                variant="tonal"
                size="small"
                class="text-caption text-left text-none justify-start"
                @click="sendQuickPrompt('Olá! Como está a frequência da minha célula nesta semana?')"
              >
                💬 "Como está a frequência da minha célula nesta semana?"
              </v-btn>
              <v-btn
                variant="tonal"
                size="small"
                class="text-caption text-left text-none justify-start"
                @click="sendQuickPrompt('Quais são os membros e visitantes cadastrados?')"
              >
                💬 "Quais são os membros e visitantes cadastrados?"
              </v-btn>
            </div>
          </div>

          <!-- Message Bubbles -->
          <div v-for="msg in chatMessages" :key="msg.id" class="message-bubble-wrapper mb-4">
            <!-- User Message -->
            <div v-if="msg.role === 'user'" class="d-flex justify-end">
              <div class="user-bubble pa-3 rounded-xl bg-primary text-white" style="max-width: 85%;">
                <div class="text-body-2" style="white-space: pre-wrap;">{{ msg.content }}</div>
                <div class="text-right text-caption opacity-60 mt-1" style="font-size: 10px !important;">
                  {{ msg.timestamp }}
                </div>
              </div>
            </div>

            <!-- Assistant Message -->
            <div v-else class="d-flex flex-column align-start" style="max-width: 92%;">
              <div class="assistant-bubble pa-3 rounded-xl bg-surface-variant border w-100">
                <div class="d-flex align-center justify-space-between mb-2 pb-1 border-b">
                  <div class="d-flex align-center ga-1">
                    <v-icon size="16" color="primary">mdi-graphql</v-icon>
                    <span class="text-caption font-weight-bold">{{ graph.name || 'Grafo' }}</span>
                  </div>
                  <v-chip v-if="msg.duration_ms" size="x-small" color="primary" variant="flat" density="compact">
                    {{ msg.duration_ms }}ms
                  </v-chip>
                </div>

                <div class="text-body-2 mb-2" style="white-space: pre-wrap;">{{ msg.content }}</div>

                <!-- Execution Steps Accordion -->
                <v-expansion-panels v-if="msg.steps && msg.steps.length" variant="accordion" density="compact" class="mt-2">
                  <v-expansion-panel>
                    <v-expansion-panel-title class="py-1 px-2 text-caption font-weight-bold" style="min-height: 32px;">
                      <v-icon size="14" color="info" class="mr-1">mdi-map-marker-path</v-icon>
                      Rastro da Execução ({{ msg.steps.length }} nós percorridos)
                    </v-expansion-panel-title>
                    <v-expansion-panel-text class="pa-2">
                      <v-timeline density="compact" side="end" class="mt-1">
                        <v-timeline-item
                          v-for="(step, idx) in msg.steps"
                          :key="idx"
                          :dot-color="step.status === 'success' ? 'primary' : 'error'"
                          size="x-small"
                        >
                          <div class="d-flex flex-column ga-1">
                            <div class="d-flex align-center justify-space-between">
                              <span class="text-caption font-weight-bold">
                                {{ step.node_label }}
                                <span class="text-medium-emphasis font-weight-regular">({{ step.node_type }})</span>
                              </span>
                              <span class="text-caption text-medium-emphasis" style="font-size: 10px !important;">{{ step.duration_ms }}ms</span>
                            </div>
                            <div class="text-caption text-medium-emphasis pa-2 rounded bg-surface font-mono" style="font-size: 10px !important; max-height: 120px; overflow-y: auto;">
                              {{ typeof step.output_data === 'object' ? JSON.stringify(step.output_data, null, 2) : step.output_data }}
                            </div>
                          </div>
                        </v-timeline-item>
                      </v-timeline>
                    </v-expansion-panel-text>
                  </v-expansion-panel>
                </v-expansion-panels>

                <div class="text-right text-caption text-medium-emphasis mt-1" style="font-size: 10px !important;">
                  {{ msg.timestamp }}
                </div>
              </div>
            </div>
          </div>

          <!-- Loading Indicator -->
          <div v-if="runningTest" class="d-flex align-center ga-2 pa-3 rounded-xl bg-surface-variant border mb-3" style="width: fit-content;">
            <v-progress-circular indeterminate size="16" width="2" color="primary"></v-progress-circular>
            <span class="text-caption text-medium-emphasis">Processando fluxo nos especialistas...</span>
          </div>
        </div>

        <!-- Chat Input Bar -->
        <div class="pa-3 border-t bg-surface">
          <div class="d-flex align-center ga-2">
            <v-textarea
              v-model="chatInput"
              placeholder="Digite sua mensagem para o grafo..."
              variant="outlined"
              density="compact"
              rows="1"
              auto-grow
              max-rows="4"
              hide-details
              :disabled="runningTest"
              @keydown.enter.exact.prevent="sendChatMessage"
            ></v-textarea>
            <v-btn
              color="primary"
              icon="mdi-send"
              size="small"
              :loading="runningTest"
              :disabled="!chatInput.trim()"
              @click="sendChatMessage"
            ></v-btn>
          </div>
        </div>
      </div>
    </v-navigation-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick, markRaw } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import axios from '@/plugins/axios'

import AgentGraphNode from '@/components/agent_graph/AgentGraphNode.vue'
import AgentGraphPropertiesPanel from '@/components/agent_graph/AgentGraphPropertiesPanel.vue'

const route = useRoute()
const router = useRouter()
const graphId = route.params.id

const { project } = useVueFlow()
const vueFlowInstance = ref(null)

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

const nodes = ref([])
const edges = ref([])
const editingName = ref(false)
const saving = ref(false)
const saveStatus = reactive({ color: 'grey', icon: 'mdi-cloud-outline', text: 'Não salvo' })
const showSettingsDialog = ref(false)
const selectedNode = ref(null)

// Floating edge styling menu variables
const selectedEdge = ref(null)
const edgeMenuPosition = ref({ x: 0, y: 0 })
const showEdgeMenu = ref(false)
const connectionColors = [
  { name: 'Azul Padrão', value: '#3B82F6' },
  { name: 'Verde (Aprovado / True)', value: '#10B981' },
  { name: 'Vermelho (False / Erro)', value: '#EF4444' },
  { name: 'Amarelo (Loop / Retry)', value: '#F59E0B' },
  { name: 'Roxo (Supervisor)', value: '#8B5CF6' },
  { name: 'Ciano (Paralelo)', value: '#06B6D4' },
  { name: 'Rosa (Sintetizador)', value: '#EC4899' },
]

// ═══ INTERACTIVE CHAT TEST STATE ═══
const showTestDrawer = ref(false)
const showContextEditor = ref(false)
const testSessionId = ref(`sess_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`)
const chatInput = ref('')
const testPayloadJson = ref('{\n  "church_name": "Igreja Central",\n  "user_name": "Fernando"\n}')
const runningTest = ref(false)
const chatMessages = ref([])
const chatContainerRef = ref(null)

const formatTestJson = () => {
  try {
    if (!testPayloadJson.value.trim()) return
    const parsed = JSON.parse(testPayloadJson.value)
    testPayloadJson.value = JSON.stringify(parsed, null, 2)
  } catch (e) {
    alert('JSON com formato inválido: ' + e.message)
  }
}

const insertExampleJson = () => {
  testPayloadJson.value = JSON.stringify({
    church_name: "Igreja Batista Central",
    user_name: "Fernando",
    user_phone: "5511999999999",
    user_role: "membro",
    current_date: new Date().toISOString().split('T')[0]
  }, null, 2)
}

const toolboxItems = [
  { type: 'start', label: 'Início / Trigger', icon: 'mdi-play-circle', color: '#10B981', category: 'flow' },
  { type: 'agent', label: 'Agente Especialista', icon: 'mdi-robot', color: '#3B82F6', category: 'agents' },
  { type: 'router', label: 'Supervisor / Router', icon: 'mdi-source-branch', color: '#8B5CF6', category: 'agents' },
  { type: 'workflow', label: 'Workflow (Dados)', icon: 'mdi-sitemap', color: '#2563EB', category: 'workflows' },
  { type: 'parallel', label: 'Fan-Out Paralelo', icon: 'mdi-call-split', color: '#06B6D4', category: 'flow' },
  { type: 'synthesizer', label: 'Sintetizador Fan-In', icon: 'mdi-call-merge', color: '#EC4899', category: 'flow' },
  { type: 'judge', label: 'Juiz de Qualidade', icon: 'mdi-scale-balance', color: '#EAB308', category: 'decision' },
  { type: 'condition', label: 'Decisão / Condição', icon: 'mdi-help-rhombus', color: '#F59E0B', category: 'decision' },
  { type: 'verifier', label: 'Verificador (Loop)', icon: 'mdi-shield-check', color: '#EAB308', category: 'decision' },
  { type: 'tool', label: 'Ação / Ferramenta', icon: 'mdi-tools', color: '#14B8A6', category: 'actions' },
  { type: 'end', label: 'Fim / Resposta', icon: 'mdi-stop-circle', color: '#64748B', category: 'actions' },
]

const onPaneReady = (instance) => {
  vueFlowInstance.value = instance
  instance.fitView()
}

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

    // Hydrate Vue Flow nodes & edges
    const rawNodes = (graph.definition.nodes || []).map(n => ({
      ...n,
      type: 'agentGraphNode',
      data: { ...n.data }
    }))
    const rawEdges = (graph.definition.edges || []).map((e, idx) => {
      const sourceHandleVal = e.sourceHandle || null
      const defaultColor = (sourceHandleVal === 'true' || sourceHandleVal === 'approved')
        ? '#10B981'
        : (sourceHandleVal === 'false')
          ? '#EF4444'
          : (sourceHandleVal === 'retry')
            ? '#F59E0B'
            : '#3B82F6'
      return {
        id: e.id || `e-${idx}-${Date.now()}`,
        source: e.source,
        target: e.target,
        sourceHandle: sourceHandleVal,
        targetHandle: e.targetHandle || null,
        label: e.label || '',
        type: 'smoothstep',
        animated: true,
        style: e.style || { stroke: defaultColor, strokeWidth: 2 }
      }
    })

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
      nodes.value = [defaultStart, defaultAgent]
      edges.value = [
        { id: 'e-start-agent', source: 'start-1', target: 'agent-1', type: 'smoothstep', animated: true, style: { stroke: '#3B82F6', strokeWidth: 2 } }
      ]
    } else {
      nodes.value = rawNodes
      edges.value = rawEdges
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
    const payload = {
      name: graph.name,
      description: graph.description,
      is_active: graph.is_active,
      recursion_limit: graph.recursion_limit,
      timeout_seconds: graph.timeout_seconds,
      definition: {
        nodes: nodes.value,
        edges: edges.value
      }
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
  event.dataTransfer.setData('application/vueflow-type', nodeType)
  event.dataTransfer.effectAllowed = 'move'
}

const onDrop = (event) => {
  event.preventDefault()
  const type = event.dataTransfer?.getData('application/vueflow-type')
  if (!type || !vueFlowInstance.value) return

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

  nodes.value = [...nodes.value, newNode]
  saveStatus.color = 'grey'
  saveStatus.icon = 'mdi-cloud-outline'
  saveStatus.text = 'Não salvo'
}

function onConnect(params) {
  const edgeId = `e-${params.source}-${params.target}-${params.sourceHandle || 'default'}-${Date.now()}`
  
  const sourceNode = nodes.value.find(n => n.id === params.source)
  let label = params.sourceHandle || ''
  let defaultColor = '#3B82F6'
  let strokeDasharray = undefined

  if (params.targetHandle === 'loop_in_left' || params.targetHandle === 'loop_in_right') {
    defaultColor = '#F59E0B'
    label = label || 'Retorno / Loop'
    strokeDasharray = '5,5'
  } else if (params.sourceHandle === 'true') {
    defaultColor = '#10B981'
    label = 'Verdadeiro'
  } else if (params.sourceHandle === 'false') {
    defaultColor = '#EF4444'
    label = 'Falso'
  } else if (params.sourceHandle === 'approved') {
    defaultColor = '#10B981'
    label = 'Aprovado (True)'
  } else if (params.sourceHandle === 'retry') {
    defaultColor = '#F59E0B'
    label = 'Loop Refazer (False)'
    strokeDasharray = '5,5'
  } else if (params.sourceHandle === 'default') {
    defaultColor = '#EF4444'
    label = 'Outro / Fallback'
  } else if (params.sourceHandle && params.sourceHandle.startsWith('route_')) {
    defaultColor = '#8B5CF6'
    const routes = sourceNode?.data?.config?.routes || []
    const r = routes.find(item => item.id === params.sourceHandle) || routes[parseInt(params.sourceHandle.replace('route_', ''))]
    if (r && r.name) {
      label = r.name
    } else {
      label = params.sourceHandle
    }
  }

  edges.value = [...edges.value, {
    id: edgeId,
    source: params.source,
    target: params.target,
    sourceHandle: params.sourceHandle || null,
    targetHandle: params.targetHandle || null,
    label,
    type: 'smoothstep',
    animated: true,
    style: { stroke: defaultColor, strokeWidth: 2, ...(strokeDasharray ? { strokeDasharray } : {}) },
  }]
  saveStatus.color = 'grey'
  saveStatus.icon = 'mdi-cloud-outline'
  saveStatus.text = 'Não salvo'
}

function onNodesChange(changes) {
  for (const c of changes) {
    if (c.type === 'position' && c.position) {
      const node = nodes.value.find(n => n.id === c.id)
      if (node) {
        node.position = c.position
        saveStatus.color = 'grey'
        saveStatus.icon = 'mdi-cloud-outline'
        saveStatus.text = 'Não salvo'
      }
    }
    if (c.type === 'remove') {
      nodes.value = nodes.value.filter(n => n.id !== c.id)
      edges.value = edges.value.filter(e => e.source !== c.id && e.target !== c.id)
      if (selectedNode.value && selectedNode.value.id === c.id) selectedNode.value = null
      saveStatus.color = 'grey'
      saveStatus.icon = 'mdi-cloud-outline'
      saveStatus.text = 'Não salvo'
    }
  }
}

function onEdgesChange(changes) {
  for (const c of changes) {
    if (c.type === 'remove') {
      edges.value = edges.value.filter(e => e.id !== c.id)
      saveStatus.color = 'grey'
      saveStatus.icon = 'mdi-cloud-outline'
      saveStatus.text = 'Não salvo'
    }
  }
}

const onNodeClick = ({ node }) => {
  selectedNode.value = node
  showEdgeMenu.value = false
}

const onPaneClick = () => {
  selectedNode.value = null
  showEdgeMenu.value = false
}

const onEdgeClick = (edgeMouseEvent) => {
  selectedEdge.value = edgeMouseEvent.edge
  const e = edgeMouseEvent.event
  if (e) {
    edgeMenuPosition.value = { x: e.clientX + 10, y: e.clientY - 20 }
    showEdgeMenu.value = true
  }
}

const setEdgeColor = (colorHex) => {
  if (!selectedEdge.value) return
  const edge = edges.value.find(e => e.id === selectedEdge.value.id)
  if (edge) {
    edge.style = { ...(edge.style || {}), stroke: colorHex }
    saveStatus.color = 'grey'
    saveStatus.icon = 'mdi-cloud-outline'
    saveStatus.text = 'Não salvo'
  }
  showEdgeMenu.value = false
}

const deleteSelectedEdge = () => {
  if (!selectedEdge.value) return
  edges.value = edges.value.filter(e => e.id !== selectedEdge.value.id)
  selectedEdge.value = null
  showEdgeMenu.value = false
  saveStatus.color = 'grey'
  saveStatus.icon = 'mdi-cloud-outline'
  saveStatus.text = 'Não salvo'
}

const deleteSelectedNode = (nodeId) => {
  nodes.value = nodes.value.filter(n => n.id !== nodeId)
  edges.value = edges.value.filter(e => e.source !== nodeId && e.target !== nodeId)
  selectedNode.value = null
  saveStatus.color = 'grey'
  saveStatus.icon = 'mdi-cloud-outline'
  saveStatus.text = 'Não salvo'
}

// ═══ CANVAS HIGHLIGHTING (LIVE TRACE / SOMBRA) ═══
function applyExecutionHighlights(steps) {
  if (!steps || !steps.length) return
  const executedNodeIds = new Set(steps.map(s => s.node_id))

  // 1. Highlight traversed nodes
  nodes.value = nodes.value.map(n => ({
    ...n,
    data: {
      ...n.data,
      _isExecuted: executedNodeIds.has(n.id),
      _status: executedNodeIds.has(n.id) ? 'success' : undefined
    }
  }))

  // 2. Highlight traversed edges with animated glow & shadow
  const executedPairs = new Set()
  for (let i = 0; i < steps.length - 1; i++) {
    executedPairs.add(`${steps[i].node_id}->${steps[i + 1].node_id}`)
  }

  edges.value = edges.value.map(e => {
    const isTraversed = executedPairs.has(`${e.source}->${e.target}`)
    if (isTraversed) {
      return {
        ...e,
        animated: true,
        style: {
          ...(e.style || {}),
          stroke: '#6366F1',
          strokeWidth: 3.5,
          filter: 'drop-shadow(0 0 8px rgba(99, 102, 241, 0.9))'
        }
      }
    } else {
      const sourceHandleVal = e.sourceHandle || e.label || null
      const defaultColor = (sourceHandleVal === 'true' || sourceHandleVal === 'approved')
        ? '#10B981'
        : (sourceHandleVal === 'false')
          ? '#EF4444'
          : (sourceHandleVal === 'retry')
            ? '#F59E0B'
            : '#3B82F6'
      return {
        ...e,
        animated: false,
        style: {
          stroke: defaultColor,
          strokeWidth: 1.5,
          opacity: 0.25
        }
      }
    }
  })
}

function clearExecutionHighlights() {
  nodes.value = nodes.value.map(n => ({
    ...n,
    data: {
      ...n.data,
      _isExecuted: false,
      _status: undefined
    }
  }))
  edges.value = edges.value.map(e => {
    const sourceHandleVal = e.sourceHandle || e.label || null
    const defaultColor = (sourceHandleVal === 'true' || sourceHandleVal === 'approved')
      ? '#10B981'
      : (sourceHandleVal === 'false')
        ? '#EF4444'
        : (sourceHandleVal === 'retry')
          ? '#F59E0B'
          : '#3B82F6'
    return {
      ...e,
      animated: true,
      style: {
        ...(e.style || {}),
        stroke: defaultColor,
        strokeWidth: 2,
        opacity: 1,
        filter: undefined
      }
    }
  })
}

// ═══ INTERACTIVE CHAT METHODS ═══
const openTestChatDrawer = () => {
  showTestDrawer.value = true
  scrollToChatBottom()
}

const resetChatSession = () => {
  testSessionId.value = `sess_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
  chatMessages.value = []
  clearExecutionHighlights()
}

const sendQuickPrompt = (promptText) => {
  chatInput.value = promptText
  sendChatMessage()
}

const scrollToChatBottom = () => {
  nextTick(() => {
    if (chatContainerRef.value) {
      chatContainerRef.value.scrollTop = chatContainerRef.value.scrollHeight
    }
  })
}

const sendChatMessage = async () => {
  const userText = chatInput.value.trim()
  if (!userText || runningTest.value) return

  let contextData = {}
  try {
    if (testPayloadJson.value && testPayloadJson.value.trim()) {
      contextData = JSON.parse(testPayloadJson.value)
    }
  } catch (e) {
    alert('JSON de Parâmetros com formato inválido: ' + e.message)
    return
  }

  // Add user bubble
  const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  chatMessages.value.push({
    id: `user_${Date.now()}`,
    role: 'user',
    content: userText,
    timestamp: now
  })
  chatInput.value = ''
  scrollToChatBottom()

  runningTest.value = true

  try {
    const currentDefinition = {
      nodes: nodes.value,
      edges: edges.value
    }

    const historyPayload = chatMessages.value.slice(0, -1).map(m => ({
      role: m.role,
      content: m.content
    }))

    const res = await axios.post(`/agent-graphs/${graphId}/test`, {
      message: userText,
      history: historyPayload,
      context_data: contextData,
      session_id: testSessionId.value,
      definition: currentDefinition
    })

    const data = res.data

    // Add assistant bubble
    chatMessages.value.push({
      id: `asst_${Date.now()}`,
      role: 'assistant',
      content: data.final_output || 'Nenhuma resposta gerada.',
      steps: data.steps || [],
      duration_ms: data.total_duration_ms,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    })

    // Highlight path on canvas
    applyExecutionHighlights(data.steps || [])
  } catch (e) {
    console.error('Erro ao testar grafo no chat:', e)
    chatMessages.value.push({
      id: `err_${Date.now()}`,
      role: 'assistant',
      content: '❌ Erro ao executar grafo: ' + (e.response?.data?.detail || e.message),
      steps: [],
      duration_ms: 0,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    })
  } finally {
    runningTest.value = false
    scrollToChatBottom()
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
.agent-graph-editor-page {
  background-color: #0F0F17;
}

.graph-name-display {
  cursor: pointer;
  transition: opacity 0.2s;
}

.graph-name-display:hover {
  opacity: 0.75;
}

.dndnode {
  border: 1px solid rgba(255, 255, 255, 0.15);
  transition: all 0.2s ease;
  user-select: none;
  color: #ffffff !important;
}

.dndnode .text-subtitle-2 {
  color: #ffffff !important;
}

.dndnode:hover {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.4);
  transform: translateY(-2px);
}

.cursor-grab {
  cursor: grab;
}

.properties-drawer, .test-chat-drawer {
  border-left: 1px solid rgba(255, 255, 255, 0.1) !important;
}

.monospace-field :deep(textarea) {
  font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
  font-size: 12px !important;
}

.chat-messages-container {
  background: #0d111d;
}

.user-bubble {
  box-shadow: 0 2px 10px rgba(59, 130, 246, 0.25);
}

.assistant-bubble {
  background: #161b2e !important;
  border-color: rgba(255, 255, 255, 0.1) !important;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.3);
}
</style>

