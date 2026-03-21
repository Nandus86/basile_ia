<template>
  <div class="workflow-editor-page d-flex flex-column" style="height: calc(100vh - 64px)">
    <!-- Header Toolbar -->
    <v-toolbar color="surface" elevation="2" class="px-4" height="60">
      <v-btn icon @click="goBack" class="mr-2">
        <v-icon>mdi-arrow-left</v-icon>
      </v-btn>
      <div class="d-flex align-center">
        <v-icon color="primary" class="mr-2">mdi-sitemap</v-icon>
        <h2 class="text-h6 mb-0">{{ workflow.name || 'Carregando...' }}</h2>
      </div>
      <v-spacer></v-spacer>
      
      <!-- Save Status -->
      <v-chip class="mr-4" :color="saveStatus.color" variant="flat" size="small">
        <v-icon start size="14">{{ saveStatus.icon }}</v-icon>
        {{ saveStatus.text }}
      </v-chip>
      


      <v-btn color="primary" @click="saveDefinition" :loading="saving" prepend-icon="mdi-content-save">
        Salvar
      </v-btn>
    </v-toolbar>

    <!-- Main Editor Body -->
    <div class="d-flex flex-grow-1" style="overflow: hidden">
      
      <!-- Toolbox Sidebar -->
      <v-navigation-drawer permanent location="left" width="300" color="surface-variant" elevation="4">
        <div class="pa-4 text-center border-b">
          <h3 class="text-subtitle-1 font-weight-bold mb-1">
            <v-icon size="20" class="mr-1">mdi-toolbox-outline</v-icon>
            Caixa de Ferramentas
          </h3>
          <p class="text-caption text-medium-emphasis">Arraste os nós para o canvas</p>
        </div>
        
        <v-list class="pt-0">
          <v-list-subheader class="font-weight-bold mt-2">Gatilhos</v-list-subheader>
          <div 
            class="dndnode trigger-node text-center ma-2 pa-3 cursor-grab rounded border"
            :draggable="true" 
            @dragstart="onDragStart($event, 'trigger')"
          >
            <v-icon color="warning" class="mb-1">mdi-lightning-bolt</v-icon>
            <div class="text-subtitle-2">Webhook</div>
          </div>
          
          <v-list-subheader class="font-weight-bold mt-2">Agentes</v-list-subheader>
          <div 
            class="dndnode orchestrator-node text-center ma-2 pa-3 cursor-grab rounded border"
            :draggable="true" 
            @dragstart="onDragStart($event, 'orchestrator')"
            v-tooltip="'Conexão Vertical (Superior/Inferior)'"
          >
            <v-icon color="purple" class="mb-1">mdi-account-supervisor</v-icon>
            <div class="text-subtitle-2">Orquestrador</div>
          </div>
          
          <div 
            class="dndnode standard-node text-center ma-2 pa-3 cursor-grab rounded border"
            :draggable="true" 
            @dragstart="onDragStart($event, 'standard')"
            v-tooltip="'Conexão Horizontal (Esquerda/Direita)'"
          >
            <v-icon color="info" class="mb-1">mdi-robot</v-icon>
            <div class="text-subtitle-2">Especialista</div>
          </div>

        </v-list>
      </v-navigation-drawer>

      <!-- Vue Flow Canvas -->
      <div 
        class="vue-flow-container flex-grow-1" 
        style="position: relative;" 
        @drop="onDrop" 
        @dragover="onDragOver"
      >
        <VueFlow
          v-model="elements"
          @pane-ready="onPaneReady"
          @node-click="onNodeClick"
          @pane-click="onPaneClick"
        >
          <!-- Controls and Background -->
          <Background pattern-color="#aaa" />
          <Controls />
          <MiniMap />
        </VueFlow>
      </div>

      <!-- Properties Sidebar -->
      <v-navigation-drawer 
        :model-value="!!selectedNode"
        location="right" 
        width="350" 
        color="surface" 
        elevation="4"
        class="properties-drawer"
      >
        <div v-if="selectedNode" class="pa-4 h-100 d-flex flex-column">
          <div class="d-flex justify-space-between align-center mb-4">
            <h3 class="text-h6 d-flex align-center">
              <v-icon :color="getNodeColor(selectedNode.type)" class="mr-2">
                {{ getNodeIcon(selectedNode.type) }}
              </v-icon>
              Propriedades
            </h3>
            <v-btn icon variant="text" size="small" @click="selectedNode = null">
              <v-icon>mdi-close</v-icon>
            </v-btn>
          </div>
          <v-divider class="mb-4"></v-divider>
          
          <v-form class="flex-grow-1 overflow-y-auto pr-2">
            <!-- Node Label -->
            <v-text-field
              v-model="selectedNode.label"
              label="Rótulo no Canvas"
              variant="outlined"
              density="compact"
            ></v-text-field>
            
            <!-- Agent Selection for standard or orchestrator -->
            <div v-if="selectedNode.type === 'standard' || selectedNode.type === 'orchestrator'">
              <v-select
                v-model="selectedNode.data.agentId"
                :items="agentsList"
                item-title="name"
                item-value="id"
                label="Vincular Agente"
                variant="outlined"
                density="compact"
                hide-details
                class="mb-4"
                clearable
              ></v-select>
              
              <v-alert v-if="!selectedNode.data.agentId" type="warning" variant="tonal" density="compact" class="mb-4 text-caption">
                Selecione um agente da base de dados.
              </v-alert>
              
              <v-textarea
                v-model="selectedNode.data.instructionsOverride"
                label="Instruções Adicionais (Override Local)"
                placeholder="Instruções ativas apenas neste fluxo..."
                variant="outlined"
                rows="3"
                density="compact"
                hide-details
              ></v-textarea>
            </div>
            
            <!-- Trigger Settings -->
            <div v-if="selectedNode.type === 'trigger'">
              <v-select
                v-model="selectedNode.data.webhookConfigId"
                :items="webhooksList"
                item-title="name"
                item-value="id"
                label="Vincular Webhook Config"
                variant="outlined"
                density="compact"
                hide-details
                class="mb-4"
                clearable
              ></v-select>
              <v-alert v-if="!selectedNode.data.webhookConfigId" type="info" variant="tonal" density="compact" class="mb-4 text-caption">
                Opcional: vincule se a entrada deste fluxo vier atráves de um webhook.
              </v-alert>
            </div>
            
          </v-form>
          
          <div class="mt-4 pt-4 border-t d-flex justify-space-between">
            <v-btn color="error" variant="text" size="small" @click="deleteSelectedNode">
              <v-icon start>mdi-trash-can</v-icon>
              Excluir Nó
            </v-btn>
          </div>
        </div>
      </v-navigation-drawer>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import axios from '@/plugins/axios'

// Vue Flow Imports
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'

// Essential core CSS
import '@vue-flow/core/dist/style.css'
// Optional default theme CSS
import '@vue-flow/core/dist/theme-default.css'

const router = useRouter()
const route = useRoute()
const workflowId = route.params.id

const elements = ref([])
const { project, viewport } = useVueFlow()
const vueFlowInstance = ref(null)

let idCounter = 1

const workflow = ref({})
const agentsList = ref([])
const webhooksList = ref([])
const saving = ref(false)
const selectedNode = ref(null)

const saveStatus = ref({ text: 'Salvo', color: 'success', icon: 'mdi-check' })





onMounted(async () => {
  await Promise.all([
    fetchAgents(),
    fetchWebhooks(),
    loadWorkflow()
  ])
})

async function fetchAgents() {
  try {
    const res = await axios.get('/agents')
    agentsList.value = res.data.agents || []
  } catch (e) {
    console.error(e)
  }
}

async function fetchWebhooks() {
  try {
    const res = await axios.get('/webhooks-config')
    webhooksList.value = res.data.webhook_configs || []
  } catch (e) {
    console.error(e)
  }
}

async function loadWorkflow() {
  try {
    const res = await axios.get(`/workflows/${workflowId}`)
    workflow.value = res.data.workflow || res.data

    // Attempt to load definition
    if (workflow.value.definition && workflow.value.definition.elements) {
      elements.value = workflow.value.definition.elements

      // update idCounter to prevent overlaps
      workflow.value.definition.elements.forEach(el => {
        if (!el.source && !el.target) {
          // is node
          const num = parseInt(el.id.split('-')[1])
          if (!isNaN(num) && num >= idCounter) {
            idCounter = num + 1
          }
        }
      })
    }
  } catch (e) {
    console.error("Failed to load workflow", e)
  }
}

const onPaneReady = (instance) => {
  vueFlowInstance.value = instance
  instance.fitView()
}

const onDragStart = (event, nodeType) => {
  if (event.dataTransfer) {
    event.dataTransfer.setData('application/vueflow', nodeType)
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
  event.preventDefault()
  const type = event.dataTransfer?.getData('application/vueflow')
  
  if (!type || !vueFlowInstance.value) return
  
  // Calculate dropping position mapped to the canvas coordinates
  const position = project({
    x: event.clientX - 300, // Account for left drawer width
    y: event.clientY - 60   // Account for top toolbar height
  })
  
  const newNode = {
    id: `node-${idCounter++}`,
    type: 'default', // Use default node with styling
    label: type === 'trigger' ? 'Novo Webhook' : (type === 'orchestrator' ? 'Orquestrador' : 'Especialista'),
    position,
    data: {
      type: type, // 'trigger', 'orchestrator', 'standard'
      agentId: null,
      webhookConfigId: null,
      instructionsOverride: ''
    },
    style: {
      background: type === 'trigger' ? '#FFCC0020' : (type === 'orchestrator' ? '#9933CC20' : '#3399FF20'),
      border: `2px solid ${type === 'trigger' ? '#FFCC00' : (type === 'orchestrator' ? '#9933CC' : '#3399FF')}`,
      borderRadius: '12px',
      padding: '12px',
      color: '#ffffff',
      fontWeight: 'bold',
      minWidth: '150px',
      minHeight: '70px'
    }
  }
  
  // Custom Handles rules via style (Pseudo-implementation until CustomNodes.vue)
  if (type === 'orchestrator') {
    // hierarchical mapping conceptually uses default (Top/Bottom usually)
  } else if (type === 'standard') {
    // Standard left/right. Vue Flow defaults to top/bottom unless forced.
  }
  
  elements.value.push(newNode)
  
  markUnsaved()
}

function onNodeClick(event) {
  selectedNode.value = event.node
}

function onPaneClick() {
  selectedNode.value = null
}

function deleteSelectedNode() {
  if (!selectedNode.value) return
  
  // Remove the node
  elements.value = elements.value.filter(e => e.id !== selectedNode.value.id)
  // Remove edges connected to it
  elements.value = elements.value.filter(e => e.source !== selectedNode.value.id && e.target !== selectedNode.value.id)
  
  selectedNode.value = null
  markUnsaved()
}

function getNodeIcon(type) {
  if (type === 'trigger') return 'mdi-lightning-bolt'
  if (type === 'orchestrator') return 'mdi-account-supervisor'
  return 'mdi-robot'
}

function getNodeColor(type) {
  if (type === 'trigger') return 'warning'
  if (type === 'orchestrator') return 'purple'
  return 'info'
}

function markUnsaved() {
  saveStatus.value = { text: 'Não Salvo', color: 'warning', icon: 'mdi-alert-circle' }
}

async function saveDefinition() {
  try {
    saving.value = true
    const payload = {
      name: workflow.value.name,
      description: workflow.value.description,
      is_active: workflow.value.is_active,
      definition: {
        elements: elements.value
      }
    }
    await axios.put(`/workflows/${workflowId}`, payload)
    saveStatus.value = { text: 'Salvo', color: 'success', icon: 'mdi-check' }

  } catch (e) {
    console.error(e)
    saveStatus.value = { text: 'Erro ao Salvar', color: 'error', icon: 'mdi-close-circle' }
  } finally {
    saving.value = false
}

function goBack() {
  router.push('/workflows')
}
</script>

<style scoped>
.workflow-editor-page {
  background-color: #121212;
}

.dndnode {
  border: 1px solid rgba(255, 255, 255, 0.2);
  transition: all 0.2s ease;
  user-select: none;
}
.dndnode:hover {
  background-color: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.5);
  transform: translateY(-2px);
}

.properties-drawer {
  border-left: 1px solid rgba(255, 255, 255, 0.1);
}
</style>
