<template>
  <div class="agent-graph-manager-page pa-6">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div class="d-flex align-center ga-3">
        <div class="header-icon-box">
          <v-icon color="primary" size="32">mdi-graph-outline</v-icon>
        </div>
        <div>
          <h1 class="text-h5 font-weight-bold mb-0">Grafos de Agentes</h1>
          <p class="text-caption text-medium-emphasis mb-0">
            Estúdio visual de orquestração multi-agente, paralelismo, loops de decisão e agentes componíveis
          </p>
        </div>
      </div>

      <v-btn color="primary" size="large" prepend-icon="mdi-plus" elevation="3" @click="openCreateDialog">
        Novo Grafo
      </v-btn>
    </div>

    <!-- Search & Filters -->
    <v-card class="pa-4 mb-6 glass-card rounded-xl">
      <v-row density="compact" align="center">
        <v-col cols="12" md="6">
          <v-text-field
            v-model="search"
            prepend-inner-icon="mdi-magnify"
            label="Buscar grafos de agentes..."
            variant="outlined"
            density="compact"
            hide-details
            clearable
            @update:model-value="fetchGraphs"
          ></v-text-field>
        </v-col>
        <v-spacer></v-spacer>
        <v-col cols="auto">
          <v-btn variant="tonal" prepend-icon="mdi-refresh" @click="fetchGraphs" :loading="loading">
            Atualizar
          </v-btn>
        </v-col>
      </v-row>
    </v-card>

    <!-- Graphs Grid -->
    <v-row v-if="graphs.length > 0">
      <v-col v-for="g in graphs" :key="g.id" cols="12" md="4" lg="3">
        <v-card class="graph-card rounded-xl pa-5 d-flex flex-column h-100 position-relative" elevation="2">
          <div class="d-flex align-center justify-space-between mb-3">
            <div class="d-flex align-center ga-2">
              <v-avatar color="primary" variant="tonal" size="36" class="rounded-lg">
                <v-icon size="20">mdi-transit-connection-variant</v-icon>
              </v-avatar>
              <h3 class="text-subtitle-1 font-weight-bold mb-0 text-truncate" style="max-width: 180px;">
                {{ g.name }}
              </h3>
            </div>
            <v-chip :color="g.is_active ? 'success' : 'grey'" size="x-small" variant="flat">
              {{ g.is_active ? 'Ativo' : 'Inativo' }}
            </v-chip>
          </div>

          <p class="text-caption text-medium-emphasis flex-grow-1 mb-4 graph-desc">
            {{ g.description || 'Sem descrição cadastrada.' }}
          </p>

          <!-- Badges -->
          <div class="d-flex align-center ga-2 mb-4">
            <v-chip size="x-small" variant="tonal" color="info" prepend-icon="mdi-cube-outline">
              {{ g.node_count }} nós
            </v-chip>
            <v-chip size="x-small" variant="tonal" color="amber-darken-2" prepend-icon="mdi-refresh">
              Limite {{ g.recursion_limit }} loops
            </v-chip>
          </div>

          <v-divider class="mb-3"></v-divider>

          <!-- Actions -->
          <div class="d-flex align-center justify-space-between">
            <v-btn
              color="primary"
              variant="flat"
              size="small"
              prepend-icon="mdi-pencil-ruler"
              @click="openEditor(g.id)"
            >
              Abrir no Estúdio
            </v-btn>

            <v-menu offset-y>
              <template v-slot:activator="{ props }">
                <v-btn icon="mdi-dots-vertical" variant="text" size="small" v-bind="props"></v-btn>
              </template>
              <v-list bg-color="#111625" class="border-thin" rounded="lg" density="compact">
                <v-list-item prepend-icon="mdi-content-copy" title="Clonar Grafo" @click="cloneGraph(g)"></v-list-item>
                <v-list-item prepend-icon="mdi-delete" title="Excluir" color="error" @click="deleteGraph(g.id)"></v-list-item>
              </v-list>
            </v-menu>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- Empty State -->
    <div v-else-if="!loading" class="text-center py-12">
      <v-icon size="64" color="grey-darken-1" class="mb-3">mdi-graph-outline</v-icon>
      <h3 class="text-h6 font-weight-bold">Nenhum Grafo de Agentes encontrado</h3>
      <p class="text-caption text-medium-emphasis mb-4">Crie seu primeiro grafo para orquestrar agentes e workflows complexos.</p>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="openCreateDialog">
        Criar Primeiro Grafo
      </v-btn>
    </div>

    <!-- Create Graph Modal -->
    <v-dialog v-model="createDialog" max-width="550">
      <v-card class="pa-5 bg-surface rounded-xl">
        <v-card-title class="font-weight-bold d-flex align-center ga-2 px-0 pt-0">
          <v-icon color="primary">mdi-plus-circle</v-icon>Novo Grafo de Agentes
        </v-card-title>

        <v-card-text class="px-0 py-2">
          <v-text-field
            v-model="newGraph.name"
            label="Nome do Grafo *"
            variant="outlined"
            density="compact"
            placeholder="Ex: Orquestrador Geral de Atendimento"
            class="mb-3"
            :rules="[v => !!v || 'Nome é obrigatório']"
          ></v-text-field>

          <v-textarea
            v-model="newGraph.description"
            label="Descrição"
            variant="outlined"
            density="compact"
            rows="2"
            placeholder="Descreva o propósito deste grafo..."
            class="mb-3"
          ></v-textarea>

          <v-select
            v-model="selectedTemplate"
            :items="templates"
            item-title="title"
            item-value="id"
            label="Modelo Inicial (Template)"
            variant="outlined"
            density="compact"
            prepend-inner-icon="mdi-file-tree"
          ></v-select>
        </v-card-text>

        <v-card-actions class="px-0 pb-0 justify-end">
          <v-btn variant="text" @click="createDialog = false">Cancelar</v-btn>
          <v-btn color="primary" variant="flat" :loading="creating" :disabled="!newGraph.name.trim()" @click="submitCreateGraph">
            Criar e Abrir Estúdio
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

const router = useRouter()

const graphs = ref([])
const loading = ref(false)
const search = ref('')

const createDialog = ref(false)
const creating = ref(false)
const newGraph = reactive({ name: '', description: '' })
const selectedTemplate = ref('supervisor_specialists')

const templates = [
  { id: 'blank', title: 'Grafo em Branco (Início + Agente)' },
  { id: 'supervisor_specialists', title: 'Time com Supervisor & Especialistas Paralelos' },
  { id: 'reasoning_loop', title: 'Loop de Decisão & Verificador (Auto-correção)' },
]

const fetchGraphs = async () => {
  loading.value = true
  try {
    const params = {}
    if (search.value) params.search = search.value
    const res = await axios.get('/agent-graphs', { params })
    graphs.value = res.data.graphs || []
  } catch (e) {
    console.error('Erro ao buscar grafos:', e)
  } finally {
    loading.value = false
  }
}

const openCreateDialog = () => {
  newGraph.name = ''
  newGraph.description = ''
  selectedTemplate.value = 'supervisor_specialists'
  createDialog.value = true
}

const submitCreateGraph = async () => {
  if (!newGraph.name.trim()) return
  creating.value = true

  // Initial nodes based on template
  let nodes = []
  let edges = []

  if (selectedTemplate.value === 'supervisor_specialists') {
    nodes = [
      { id: 'start-1', type: 'agentGraphNode', position: { x: 50, y: 150 }, data: { type: 'start', label: 'Início', config: {} } },
      { id: 'sup-1', type: 'agentGraphNode', position: { x: 280, y: 150 }, data: { type: 'router', label: 'Supervisor Router', config: {} } },
      { id: 'par-1', type: 'agentGraphNode', position: { x: 520, y: 150 }, data: { type: 'parallel', label: 'Disparo Paralelo', config: {} } },
      { id: 'ag-1', type: 'agentGraphNode', position: { x: 760, y: 80 }, data: { type: 'agent', label: 'Especialista 1', config: {} } },
      { id: 'ag-2', type: 'agentGraphNode', position: { x: 760, y: 240 }, data: { type: 'agent', label: 'Especialista 2', config: {} } },
      { id: 'synth-1', type: 'agentGraphNode', position: { x: 1020, y: 150 }, data: { type: 'synthesizer', label: 'Sintetizador', config: {} } },
      { id: 'end-1', type: 'agentGraphNode', position: { x: 1260, y: 150 }, data: { type: 'end', label: 'Resposta Final', config: {} } },
    ]
    edges = [
      { id: 'e1', source: 'start-1', target: 'sup-1', type: 'smoothstep' },
      { id: 'e2', source: 'sup-1', target: 'par-1', type: 'smoothstep' },
      { id: 'e3', source: 'par-1', target: 'ag-1', type: 'smoothstep' },
      { id: 'e4', source: 'par-1', target: 'ag-2', type: 'smoothstep' },
      { id: 'e5', source: 'ag-1', target: 'synth-1', type: 'smoothstep' },
      { id: 'e6', source: 'ag-2', target: 'synth-1', type: 'smoothstep' },
      { id: 'e7', source: 'synth-1', target: 'end-1', type: 'smoothstep' },
    ]
  } else if (selectedTemplate.value === 'reasoning_loop') {
    nodes = [
      { id: 'start-1', type: 'agentGraphNode', position: { x: 80, y: 150 }, data: { type: 'start', label: 'Início', config: {} } },
      { id: 'ag-1', type: 'agentGraphNode', position: { x: 320, y: 150 }, data: { type: 'agent', label: 'Agente Executor', config: {} } },
      { id: 'ver-1', type: 'agentGraphNode', position: { x: 580, y: 150 }, data: { type: 'verifier', label: 'Verificador de Qualidade', config: { max_retries: 2 } } },
      { id: 'end-1', type: 'agentGraphNode', position: { x: 840, y: 150 }, data: { type: 'end', label: 'Fim Aprovado', config: {} } },
    ]
    edges = [
      { id: 'e1', source: 'start-1', target: 'ag-1', type: 'smoothstep' },
      { id: 'e2', source: 'ag-1', target: 'ver-1', type: 'smoothstep' },
      { id: 'e3', source: 'ver-1', target: 'end-1', sourceHandle: 'approved', type: 'smoothstep' },
      { id: 'e4', source: 'ver-1', target: 'ag-1', sourceHandle: 'retry', label: 'Loop Correção', type: 'smoothstep' },
    ]
  } else {
    nodes = [
      { id: 'start-1', type: 'agentGraphNode', position: { x: 100, y: 200 }, data: { type: 'start', label: 'Início', config: {} } },
      { id: 'agent-1', type: 'agentGraphNode', position: { x: 380, y: 200 }, data: { type: 'agent', label: 'Agente Especialista', config: {} } },
      { id: 'end-1', type: 'agentGraphNode', position: { x: 650, y: 200 }, data: { type: 'end', label: 'Fim', config: {} } },
    ]
    edges = [
      { id: 'e1', source: 'start-1', target: 'agent-1', type: 'smoothstep' },
      { id: 'e2', source: 'agent-1', target: 'end-1', type: 'smoothstep' },
    ]
  }

  try {
    const res = await axios.post('/agent-graphs', {
      name: newGraph.name,
      description: newGraph.description,
      is_active: true,
      definition: { nodes, edges }
    })
    createDialog.value = false
    router.push(`/agent-graphs/${res.data.id}`)
  } catch (e) {
    console.error('Erro ao criar grafo:', e)
  } finally {
    creating.value = false
  }
}

const openEditor = (id) => {
  router.push(`/agent-graphs/${id}`)
}

const cloneGraph = async (g) => {
  try {
    await axios.post('/agent-graphs', {
      name: `${g.name} (Cópia)`,
      description: g.description,
      is_active: true,
      definition: g.definition || {}
    })
    fetchGraphs()
  } catch (e) {
    console.error('Erro ao clonar grafo:', e)
  }
}

const deleteGraph = async (id) => {
  if (confirm('Tem certeza que deseja excluir este grafo de agentes?')) {
    try {
      await axios.delete(`/agent-graphs/${id}`)
      fetchGraphs()
    } catch (e) {
      console.error('Erro ao excluir grafo:', e)
    }
  }
}

onMounted(() => {
  fetchGraphs()
})
</script>

<style scoped>
.header-icon-box {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: rgba(59, 130, 246, 0.15);
  display: flex;
  align-items: center;
  justify-content: center;
}

.graph-card {
  background: rgba(22, 27, 46, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.1);
  transition: all 0.2s ease;
}

.graph-card:hover {
  border-color: rgba(59, 130, 246, 0.5);
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.4);
  transform: translateY(-2px);
}

.graph-desc {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 36px;
}
</style>
