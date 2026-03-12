<template>
  <div class="workflows-page">
    <div class="page-header">
      <div class="header-content">
        <div class="header-icon">
          <v-icon size="32" color="primary">mdi-sitemap</v-icon>
        </div>
        <div class="header-text">
          <h1>Workflows Visuais</h1>
          <p>Crie orquestrações complexas de agentes em um formato visual</p>
        </div>
      </div>
      <v-btn color="primary" size="large" prepend-icon="mdi-plus" @click="createWorkflow" elevation="3">
        Novo Workflow
      </v-btn>
    </div>

    <v-card class="workflows-card glass-card">
      <v-card-title class="d-flex align-center px-6 py-4">
        <v-icon class="mr-2" color="primary">mdi-format-list-bulleted</v-icon>
        <span class="text-white">Lista de Workflows</span>
        <v-spacer></v-spacer>
        <v-text-field
          v-model="search"
          density="compact"
          placeholder="Buscar workflow..."
          prepend-inner-icon="mdi-magnify"
          variant="outlined"
          hide-details
          class="search-field"
          style="max-width: 300px"
        ></v-text-field>
      </v-card-title>
      
      <v-divider></v-divider>
      
      <v-data-table
        :headers="headers"
        :items="filteredWorkflows"
        :loading="loading"
        :items-per-page="10"
        class="workflows-table"
      >
        <template v-slot:item.name="{ item }">
          <div class="d-flex align-center py-2">
            <v-avatar color="primary" size="36" class="mr-3">
              <v-icon color="white" size="20">mdi-sitemap</v-icon>
            </v-avatar>
            <div>
              <span class="font-weight-bold">{{ item.name }}</span>
              <p class="text-caption text-medium-emphasis mb-0" v-if="item.description">
                {{ item.description?.substring(0, 50) }}{{ item.description?.length > 50 ? '...' : '' }}
              </p>
            </div>
          </div>
        </template>
        
        <template v-slot:item.is_active="{ item }">
          <v-chip :color="item.is_active ? 'success' : 'error'" size="small" variant="tonal">
            <v-icon start size="14">{{ item.is_active ? 'mdi-check' : 'mdi-close' }}</v-icon>
            {{ item.is_active ? 'Ativo' : 'Inativo' }}
          </v-chip>
        </template>
        
        <template v-slot:item.actions="{ item }">
          <div class="d-flex gap-1 justify-center">
            <v-btn icon variant="text" size="small" color="primary" @click="editWorkflow(item)">
              <v-icon size="20">mdi-vector-polyline-edit</v-icon>
              <v-tooltip activator="parent" location="top">Editor Visual</v-tooltip>
            </v-btn>
            <v-btn icon variant="text" size="small" color="error" @click="confirmDelete(item)">
              <v-icon size="20">mdi-delete</v-icon>
              <v-tooltip activator="parent" location="top">Excluir</v-tooltip>
            </v-btn>
          </div>
        </template>
        
        <template v-slot:no-data>
          <div class="text-center py-8">
            <v-icon size="64" color="grey-lighten-1" class="mb-4">mdi-sitemap-outline</v-icon>
            <p class="text-h6 text-medium-emphasis">Nenhum workflow encontrado</p>
            <v-btn color="primary" class="mt-4" @click="createWorkflow">
              <v-icon start>mdi-plus</v-icon>
              Criar Workflow
            </v-btn>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Dialog Create Workflow (Basic Metadata) -->
    <v-dialog v-model="createDialog" max-width="500">
      <v-card>
        <v-card-title class="bg-primary text-white d-flex align-center">
          <v-icon class="mr-2">mdi-plus-circle</v-icon>
          Novo Workflow
          <v-spacer></v-spacer>
          <v-btn icon variant="text" color="white" @click="createDialog = false"><v-icon>mdi-close</v-icon></v-btn>
        </v-card-title>
        <v-card-text class="pt-6">
          <v-form ref="formRef" v-model="formValid" @submit.prevent="saveNewWorkflow">
            <v-text-field
              v-model="newWorkflowData.name"
              label="Nome do Workflow"
              :rules="[v => !!v || 'Nome é obrigatório']"
              variant="outlined"
              class="mb-4"
            ></v-text-field>
            <v-textarea
              v-model="newWorkflowData.description"
              label="Descrição"
              variant="outlined"
              rows="3"
            ></v-textarea>
          </v-form>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="createDialog = false">Cancelar</v-btn>
          <v-btn color="primary" @click="saveNewWorkflow" :disabled="!formValid" :loading="saving">Criar e Editar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from '@/plugins/axios'

const router = useRouter()

const loading = ref(false)
const search = ref('')
const workflows = ref([])

const createDialog = ref(false)
const saving = ref(false)
const formValid = ref(false)
const newWorkflowData = ref({
  name: '',
  description: ''
})

const headers = [
  { title: 'Workflow', key: 'name', sortable: true },
  { title: 'Status', key: 'is_active', sortable: true },
  { title: 'Ações', key: 'actions', sortable: false, align: 'center', width: '120px' }
]

const filteredWorkflows = computed(() => {
  if (!search.value) return workflows.value
  const s = search.value.toLowerCase()
  return workflows.value.filter(w => 
    w.name.toLowerCase().includes(s) || 
    (w.description && w.description.toLowerCase().includes(s))
  )
})

onMounted(() => {
  fetchWorkflows()
})

async function fetchWorkflows() {
  loading.value = true
  try {
    const response = await axios.get('/workflows')
    workflows.value = response.data.workflows || []
  } catch (error) {
    console.error('Error fetching workflows:', error)
  } finally {
    loading.value = false
  }
}

function createWorkflow() {
  newWorkflowData.value = { name: '', description: '' }
  createDialog.value = true
}

async function saveNewWorkflow() {
  if (!formValid.value) return
  saving.value = true
  try {
    const response = await axios.post('/workflows', {
      ...newWorkflowData.value,
      is_active: true,
      definition: { nodes: [], edges: [] }
    })
    createDialog.value = false
    // Go directly to editor
    router.push(`/workflows/${response.data.id}`)
  } catch (error) {
    console.error('Error creating workflow:', error)
  } finally {
    saving.value = false
  }
}

function editWorkflow(workflow) {
  router.push(`/workflows/${workflow.id}`)
}

async function confirmDelete(workflow) {
  if (confirm(`Tem certeza que deseja excluir o workflow "${workflow.name}"?`)) {
    try {
      await axios.delete(`/workflows/${workflow.id}`)
      await fetchWorkflows()
    } catch (error) {
      console.error('Error deleting workflow:', error)
    }
  }
}
</script>

<style scoped>
.workflows-page {
  padding: 24px;
}
</style>
