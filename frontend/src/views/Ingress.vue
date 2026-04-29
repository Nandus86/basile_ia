<script setup>
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'

const pipelines = ref([])
const totalPipelines = ref(0)
const loading = ref(false)
const dialog = ref(false)
const deleteDialog = ref(false)
const isSaving = ref(false)
const isDeleting = ref(false)
const pipelineToDelete = ref(null)
const serviceOnline = ref(null)

const INGRESS_BASE = '/ingress-api'

const ingressAxios = axios.create({
  baseURL: INGRESS_BASE,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' }
})

const defaultItem = {
  name: '',
  path: '',
  is_active: true,
  description: '',
  input_schema: {
    messageRequired: true,
    sessionIdField: 'session_id',
    mappings: {},
    defaults: {}
  },
  auth_type: 'none',
  auth_token: '',
  output_url: '',
  output_method: 'POST',
  output_schema: null,
  output_headers: null,
  retry_config: { maxRetries: 3, delays: [5000, 15000, 60000] }
}

const editedItem = ref(JSON.parse(JSON.stringify(defaultItem)))
const isEditing = ref(false)

const snackbar = ref({
  show: false,
  text: '',
  color: 'success'
})

const showToken = ref(false)

const headers = [
  { title: 'NOME', key: 'name' },
  { title: 'PATH', key: 'path' },
  { title: 'DESTINO', key: 'output_url' },
  { title: 'MÉTODO', key: 'output_method', align: 'center' },
  { title: 'AUTH', key: 'auth_type', align: 'center' },
  { title: 'STATUS', key: 'is_active', align: 'center' },
  { title: 'AÇÕES', key: 'actions', sortable: false, align: 'end' }
]

const activeCount = computed(() => pipelines.value.filter(p => p.is_active).length)
const authCount = computed(() => pipelines.value.filter(p => p.auth_type !== 'none' && p.has_auth_token).length)

const checkHealth = async () => {
  try {
    const res = await ingressAxios.get('/health')
    serviceOnline.value = res.data?.status === 'healthy'
  } catch {
    serviceOnline.value = false
  }
}

const fetchPipelines = async () => {
  loading.value = true
  try {
    const res = await ingressAxios.get('/pipelines')
    pipelines.value = res.data.pipelines
    totalPipelines.value = res.data.total
  } catch (err) {
    showSnackbar('Erro ao carregar pipelines', 'error')
  } finally {
    loading.value = false
  }
}

const showSnackbar = (text, color = 'success') => {
  snackbar.value = { show: true, text, color }
}

const closeDialog = () => {
  dialog.value = false
  setTimeout(() => {
    editedItem.value = JSON.parse(JSON.stringify(defaultItem))
    isEditing.value = false
  }, 300)
}

const editPipeline = (item) => {
  const copy = JSON.parse(JSON.stringify(item))
  // Ensure input_schema has all fields
  if (!copy.input_schema) {
    copy.input_schema = { ...defaultItem.input_schema }
  }
  editedItem.value = copy
  isEditing.value = true
  dialog.value = true
}

const confirmDelete = (item) => {
  pipelineToDelete.value = item
  deleteDialog.value = true
}

const deletePipeline = async () => {
  if (!pipelineToDelete.value) return
  isDeleting.value = true
  try {
    await ingressAxios.delete(`/pipelines/${pipelineToDelete.value.id}`)
    showSnackbar('Pipeline excluído com sucesso')
    await fetchPipelines()
  } catch (err) {
    showSnackbar('Erro ao excluir pipeline', 'error')
  } finally {
    isDeleting.value = false
    deleteDialog.value = false
    pipelineToDelete.value = null
  }
}

const savePipeline = async () => {
  isSaving.value = true
  try {
    const payload = { ...editedItem.value }
    // Clean empty auth_token
    if (payload.auth_type === 'none') {
      payload.auth_token = null
    }
    
    if (isEditing.value) {
      await ingressAxios.put(`/pipelines/${payload.id}`, payload)
      showSnackbar('Pipeline atualizado com sucesso')
    } else {
      await ingressAxios.post('/pipelines', payload)
      showSnackbar('Pipeline criado com sucesso')
    }
    closeDialog()
    await fetchPipelines()
  } catch (err) {
    showSnackbar(err.response?.data?.detail || 'Erro ao salvar pipeline', 'error')
  } finally {
    isSaving.value = false
  }
}

const generateToken = () => {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
  let result = 'ing_'
  for (let i = 0; i < 32; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length))
  }
  editedItem.value.auth_token = result
}

const webhookUrl = computed(() => {
  const origin = window.location.origin
  const path = editedItem.value.path || 'meu-webhook'
  return `${origin}/ingress-api/webhook/${path}`
})

// Mapping helpers
const mappingEntries = ref([])

const syncMappingsFromItem = () => {
  const m = editedItem.value.input_schema?.mappings || {}
  mappingEntries.value = Object.entries(m).map(([k, v]) => ({ from: k, to: v }))
}

const syncMappingsToItem = () => {
  const obj = {}
  mappingEntries.value.forEach(e => {
    if (e.from && e.to) obj[e.from] = e.to
  })
  editedItem.value.input_schema.mappings = obj
}

const addMapping = () => {
  mappingEntries.value.push({ from: '', to: '' })
}

const removeMapping = (index) => {
  mappingEntries.value.splice(index, 1)
  syncMappingsToItem()
}

// Watch dialog open to sync
const openCreate = () => {
  editedItem.value = JSON.parse(JSON.stringify(defaultItem))
  isEditing.value = false
  mappingEntries.value = []
  dialog.value = true
}

const openEdit = (item) => {
  editPipeline(item)
  syncMappingsFromItem()
}

onMounted(() => {
  checkHealth()
  fetchPipelines()
})
</script>

<template>
  <div class="ingress-container">
    <!-- Header -->
    <div class="d-flex align-center mb-6">
      <v-avatar color="teal" variant="tonal" rounded size="48" class="mr-4">
        <v-icon icon="mdi-login-variant" size="24"></v-icon>
      </v-avatar>
      <div>
        <h2 class="text-h4 font-weight-bold">Entrada (Ingress)</h2>
        <div class="text-subtitle-1 text-medium-emphasis">
          Gerencie pipelines de webhook de entrada
        </div>
      </div>
      <v-spacer></v-spacer>
      <v-chip
        :color="serviceOnline === true ? 'success' : serviceOnline === false ? 'error' : 'grey'"
        variant="tonal"
        class="mr-3"
        size="small"
      >
        <v-icon start size="12">mdi-circle</v-icon>
        {{ serviceOnline === true ? 'Online' : serviceOnline === false ? 'Offline' : 'Verificando...' }}
      </v-chip>
      <v-btn color="teal" prepend-icon="mdi-plus" @click="openCreate">
        Novo Pipeline
      </v-btn>
    </div>

    <!-- Stats -->
    <v-row class="mb-6">
      <v-col cols="12" md="3">
        <v-card class="glass-card" variant="flat">
          <v-card-text>
            <div class="text-overline mb-1">TOTAL PIPELINES</div>
            <div class="text-h4 font-weight-bold">{{ totalPipelines }}</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="3">
        <v-card class="glass-card" variant="flat">
          <v-card-text>
            <div class="text-overline mb-1">ATIVOS</div>
            <div class="text-h4 font-weight-bold text-success">{{ activeCount }}</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="3">
        <v-card class="glass-card" variant="flat">
          <v-card-text>
            <div class="text-overline mb-1">COM AUTENTICAÇÃO</div>
            <div class="text-h4 font-weight-bold text-info">{{ authCount }}</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="3">
        <v-card class="glass-card" variant="flat">
          <v-card-text>
            <div class="text-overline mb-1">SERVIÇO</div>
            <div class="text-h4 font-weight-bold" :class="serviceOnline ? 'text-success' : 'text-error'">
              {{ serviceOnline ? 'OK' : 'OFF' }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Table -->
    <v-card class="glass-card" variant="flat">
      <v-data-table
        :headers="headers"
        :items="pipelines"
        :loading="loading"
        hover
      >
        <template #item.path="{ item }">
          <v-chip variant="outlined" color="teal" size="small">
            /webhook/{{ item.path }}
          </v-chip>
        </template>

        <template #item.output_url="{ item }">
          <span class="text-caption" style="max-width: 200px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
            {{ item.output_url }}
          </span>
        </template>

        <template #item.output_method="{ item }">
          <v-chip :color="item.output_method === 'POST' ? 'success' : 'warning'" size="x-small" variant="tonal">
            {{ item.output_method }}
          </v-chip>
        </template>

        <template #item.auth_type="{ item }">
          <v-chip
            :color="item.auth_type !== 'none' ? 'warning' : 'grey'"
            size="x-small"
            variant="tonal"
          >
            <v-icon start size="12">{{ item.auth_type !== 'none' ? 'mdi-lock' : 'mdi-lock-open-variant' }}</v-icon>
            {{ item.auth_type }}
          </v-chip>
        </template>

        <template #item.is_active="{ item }">
          <v-chip
            :color="item.is_active ? 'success' : 'grey'"
            size="x-small"
            variant="tonal"
          >
            {{ item.is_active ? 'Ativo' : 'Inativo' }}
          </v-chip>
        </template>

        <template #item.actions="{ item }">
          <div class="d-flex justify-end gap-2">
            <v-btn icon variant="text" size="small" color="primary" @click="openEdit(item)">
              <v-icon icon="mdi-pencil-outline"></v-icon>
              <v-tooltip activator="parent" location="top">Editar</v-tooltip>
            </v-btn>
            <v-btn icon variant="text" size="small" color="error" @click="confirmDelete(item)">
              <v-icon icon="mdi-trash-can-outline"></v-icon>
              <v-tooltip activator="parent" location="top">Excluir</v-tooltip>
            </v-btn>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Create/Edit Dialog -->
    <v-dialog v-model="dialog" max-width="900" persistent>
      <v-card class="glass-card">
        <v-card-title class="d-flex align-center pa-6 pb-4">
          <span class="text-h5 font-weight-bold">{{ isEditing ? 'Editar' : 'Novo' }} Pipeline de Entrada</span>
          <v-spacer></v-spacer>
          <v-btn icon="mdi-close" variant="text" @click="closeDialog"></v-btn>
        </v-card-title>

        <v-card-text class="px-6 py-2">
          <v-form @submit.prevent="savePipeline" id="pipeline-form">
            <!-- Basic -->
            <div class="text-subtitle-1 font-weight-bold mb-3">Informações Básicas</div>
            <v-row>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="editedItem.name"
                  label="Nome do Pipeline"
                  variant="outlined"
                  required
                ></v-text-field>
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="editedItem.path"
                  label="Path (slug ex: meu-webhook)"
                  prefix="/webhook/"
                  variant="outlined"
                  required
                ></v-text-field>
              </v-col>
            </v-row>
            <v-row>
              <v-col cols="12">
                <v-textarea
                  v-model="editedItem.description"
                  label="Descrição (Opcional)"
                  variant="outlined"
                  rows="2"
                  auto-grow
                ></v-textarea>
              </v-col>
            </v-row>

            <v-divider class="my-4"></v-divider>

            <!-- Auth -->
            <div class="text-subtitle-1 font-weight-bold mb-3">Autenticação</div>
            <v-row>
              <v-col cols="12" md="4">
                <v-select
                  v-model="editedItem.auth_type"
                  :items="['none', 'bearer', 'header', 'query']"
                  label="Tipo de Auth"
                  variant="outlined"
                ></v-select>
              </v-col>
              <v-col cols="12" md="8" v-if="editedItem.auth_type !== 'none'">
                <v-text-field
                  v-model="editedItem.auth_token"
                  label="Token de Autenticação"
                  variant="outlined"
                  :type="showToken ? 'text' : 'password'"
                  :append-inner-icon="showToken ? 'mdi-eye-off' : 'mdi-eye'"
                  @click:append-inner="showToken = !showToken"
                >
                  <template v-slot:append>
                    <v-btn color="secondary" variant="tonal" @click="generateToken">Gerar</v-btn>
                  </template>
                </v-text-field>
              </v-col>
            </v-row>

            <v-divider class="my-4"></v-divider>

            <!-- Input Schema -->
            <div class="text-subtitle-1 font-weight-bold mb-3">Esquema de Entrada</div>
            <v-row>
              <v-col cols="12" md="6">
                <v-switch
                  v-model="editedItem.input_schema.messageRequired"
                  color="primary"
                  label="Mensagem obrigatória"
                  hint="Exige campo de mensagem no payload"
                  persistent-hint
                ></v-switch>
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="editedItem.input_schema.sessionIdField"
                  label="Campo de Session ID"
                  variant="outlined"
                  hint="Nome do campo que contém o ID da sessão"
                  persistent-hint
                ></v-text-field>
              </v-col>
            </v-row>

            <!-- Mappings -->
            <div class="mt-4 bg-surface-variant pa-4 rounded-lg">
              <div class="d-flex align-center mb-3">
                <span class="font-weight-medium">Mapeamento de Campos</span>
                <v-spacer></v-spacer>
                <v-btn size="small" color="teal" variant="tonal" prepend-icon="mdi-plus" @click="addMapping">
                  Adicionar
                </v-btn>
              </div>
              <div v-for="(entry, index) in mappingEntries" :key="index" class="d-flex gap-2 mb-2 align-center">
                <v-text-field v-model="entry.from" label="Campo externo" variant="outlined" density="compact" hide-details @blur="syncMappingsToItem"></v-text-field>
                <v-icon size="20" class="mx-1">mdi-arrow-right</v-icon>
                <v-text-field v-model="entry.to" label="Campo interno" variant="outlined" density="compact" hide-details @blur="syncMappingsToItem"></v-text-field>
                <v-btn icon color="error" variant="text" size="small" @click="removeMapping(index)">
                  <v-icon icon="mdi-trash-can-outline"></v-icon>
                </v-btn>
              </div>
              <div v-if="mappingEntries.length === 0" class="text-caption text-medium-emphasis">
                Nenhum mapeamento configurado.
              </div>
            </div>

            <v-divider class="my-4"></v-divider>

            <!-- Output -->
            <div class="text-subtitle-1 font-weight-bold mb-3">Destino (Output)</div>
            <v-row>
              <v-col cols="12" md="8">
                <v-text-field
                  v-model="editedItem.output_url"
                  label="URL de destino"
                  variant="outlined"
                  hint="URL para onde o payload normalizado será enviado"
                  persistent-hint
                  required
                ></v-text-field>
              </v-col>
              <v-col cols="12" md="4">
                <v-select
                  v-model="editedItem.output_method"
                  :items="['POST', 'PUT', 'PATCH']"
                  label="Método HTTP"
                  variant="outlined"
                ></v-select>
              </v-col>
            </v-row>

            <v-divider class="my-4"></v-divider>

            <!-- Retry Config -->
            <div class="text-subtitle-1 font-weight-bold mb-3">Retentativas</div>
            <v-row>
              <v-col cols="12" md="4">
                <v-text-field
                  v-model.number="editedItem.retry_config.maxRetries"
                  type="number"
                  label="Máximo de Retentativas"
                  variant="outlined"
                  min="0"
                ></v-text-field>
              </v-col>
            </v-row>

            <v-row>
              <v-col cols="12">
                <v-switch
                  v-model="editedItem.is_active"
                  color="success"
                  label="Pipeline Ativo"
                ></v-switch>
              </v-col>
            </v-row>
          </v-form>
        </v-card-text>

        <v-divider></v-divider>
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="closeDialog" :disabled="isSaving">Cancelar</v-btn>
          <v-btn
            color="teal"
            variant="flat"
            type="submit"
            form="pipeline-form"
            :loading="isSaving"
            class="px-6"
          >
            Salvar
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete Dialog -->
    <v-dialog v-model="deleteDialog" max-width="500">
      <v-card class="glass-card">
        <v-card-title class="text-h5 font-weight-bold error--text pa-6 pb-4">
          <v-icon icon="mdi-alert" color="error" class="mr-2"></v-icon>
          Confirmar Exclusão
        </v-card-title>
        <v-card-text class="px-6 py-2">
          Tem certeza que deseja excluir o pipeline <strong>{{ pipelineToDelete?.name }}</strong>?<br>
          Esta ação não pode ser desfeita.
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="deleteDialog = false" :disabled="isDeleting">Cancelar</v-btn>
          <v-btn
            color="error"
            variant="flat"
            @click="deletePipeline"
            :loading="isDeleting"
            class="px-6"
          >
            Excluir
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      location="top"
      :timeout="3000"
    >
      {{ snackbar.text }}
      <template v-slot:actions>
        <v-btn variant="text" @click="snackbar.show = false">Fechar</v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<style scoped>
.ingress-container {
  max-width: 1400px;
  margin: 0 auto;
}
.glass-card {
  background: rgba(var(--v-theme-surface), 0.7) !important;
  backdrop-filter: blur(10px);
  border: 1px solid rgba(var(--v-border-color), 0.1);
}
.gap-2 {
  gap: 8px;
}
</style>
