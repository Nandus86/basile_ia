<script setup>
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'

// --- Tabs State ---
const currentTab = ref('results')

// --- Common State ---
const loading = ref(false)
const serviceOnline = ref(null)
const snackbar = ref({ show: false, text: '', color: 'success' })

const EGRESS_BASE = '/egress-api'
const egressAxios = axios.create({
  baseURL: EGRESS_BASE,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' }
})

const showSnackbar = (text, color = 'success') => {
  snackbar.value = { show: true, text, color }
}

const checkHealth = async () => {
  try {
    const res = await egressAxios.get('/health')
    serviceOnline.value = res.data?.status === 'healthy'
  } catch {
    serviceOnline.value = false
  }
}

// --- Results State (Aba Resultados) ---
const results = ref([])
const totalResults = ref(0)
const statusFilter = ref(null)
const detailDialog = ref(false)
const selectedResult = ref(null)

const resultHeaders = [
  { title: 'JOB ID', key: 'job_id' },
  { title: 'STATUS', key: 'status', align: 'center' },
  { title: 'TENTATIVAS', key: 'attempts', align: 'center' },
  { title: 'ERRO', key: 'last_error' },
  { title: 'AÇÕES', key: 'actions', sortable: false, align: 'end' }
]

const statusOptions = [
  { title: 'Todos', value: null },
  { title: 'Pendente', value: 'pending' },
  { title: 'Processando', value: 'processing' },
  { title: 'Enviado', value: 'sent' },
  { title: 'Falha', value: 'failed' }
]

const sentCount = computed(() => results.value.filter(r => r.status === 'sent').length)
const failedCount = computed(() => results.value.filter(r => r.status === 'failed').length)
const pendingCount = computed(() => results.value.filter(r => r.status === 'pending' || r.status === 'processing').length)

const statusColor = (status) => {
  const map = {
    pending: 'warning',
    processing: 'info',
    sent: 'success',
    failed: 'error',
    unknown: 'grey'
  }
  return map[status] || 'grey'
}

const statusIcon = (status) => {
  const map = {
    pending: 'mdi-clock-outline',
    processing: 'mdi-loading mdi-spin',
    sent: 'mdi-check-circle-outline',
    failed: 'mdi-alert-circle-outline',
    unknown: 'mdi-help-circle-outline'
  }
  return map[status] || 'mdi-help-circle-outline'
}

const fetchResults = async () => {
  loading.value = true
  try {
    const params = {}
    if (statusFilter.value) params.status = statusFilter.value
    const res = await egressAxios.get('/status', { params })
    results.value = res.data.results
    totalResults.value = res.data.total
  } catch (err) {
    showSnackbar('Erro ao carregar resultados', 'error')
  } finally {
    loading.value = false
  }
}

const viewResultDetail = async (item) => {
  try {
    const res = await egressAxios.get(`/status/${item.job_id}`)
    selectedResult.value = res.data
    detailDialog.value = true
  } catch {
    showSnackbar('Erro ao buscar detalhes do resultado', 'error')
  }
}


// --- Pipelines State (Aba Pipelines) ---
const pipelines = ref([])
const totalPipelines = ref(0)
const pipelineDialog = ref(false)
const pipelineDeleteDialog = ref(false)
const isSaving = ref(false)
const isDeleting = ref(false)
const pipelineToDelete = ref(null)

const activePipelinesCount = computed(() => pipelines.value.filter(p => p.is_active).length)

const pipelineHeaders = [
  { title: 'NOME', key: 'name' },
  { title: 'PATH', key: 'path' },
  { title: 'DESTINO', key: 'output_url' },
  { title: 'MÉTODO', key: 'output_method', align: 'center' },
  { title: 'STATUS', key: 'is_active', align: 'center' },
  { title: 'AÇÕES', key: 'actions', sortable: false, align: 'end' }
]

const defaultPipelineItem = {
  name: '',
  path: '',
  is_active: true,
  description: '',
  output_url: '',
  output_method: 'POST',
  output_schema: null,
  output_headers: null,
  retry_config: { maxRetries: 3, delays: [5000, 15000, 60000] }
}

const editedPipelineItem = ref(JSON.parse(JSON.stringify(defaultPipelineItem)))
const isEditingPipeline = ref(false)

const fetchPipelines = async () => {
  loading.value = true
  try {
    const res = await egressAxios.get('/pipelines')
    pipelines.value = res.data.pipelines
    totalPipelines.value = res.data.total
  } catch (err) {
    showSnackbar('Erro ao carregar pipelines', 'error')
  } finally {
    loading.value = false
  }
}

const openCreatePipeline = () => {
  editedPipelineItem.value = JSON.parse(JSON.stringify(defaultPipelineItem))
  isEditingPipeline.value = false
  pipelineDialog.value = true
}

const openEditPipeline = (item) => {
  const copy = JSON.parse(JSON.stringify(item))
  if (!copy.retry_config) {
    copy.retry_config = { maxRetries: 3, delays: [5000, 15000, 60000] }
  }
  editedPipelineItem.value = copy
  isEditingPipeline.value = true
  pipelineDialog.value = true
}

const closePipelineDialog = () => {
  pipelineDialog.value = false
  setTimeout(() => {
    editedPipelineItem.value = JSON.parse(JSON.stringify(defaultPipelineItem))
    isEditingPipeline.value = false
  }, 300)
}

const savePipeline = async () => {
  isSaving.value = true
  try {
    const payload = { ...editedPipelineItem.value }
    if (isEditingPipeline.value) {
      await egressAxios.put(`/pipelines/${payload.id}`, payload)
      showSnackbar('Pipeline atualizado com sucesso')
    } else {
      await egressAxios.post('/pipelines', payload)
      showSnackbar('Pipeline criado com sucesso')
    }
    closePipelineDialog()
    await fetchPipelines()
  } catch (err) {
    showSnackbar(err.response?.data?.detail || 'Erro ao salvar pipeline', 'error')
  } finally {
    isSaving.value = false
  }
}

const confirmDeletePipeline = (item) => {
  pipelineToDelete.value = item
  pipelineDeleteDialog.value = true
}

const deletePipeline = async () => {
  if (!pipelineToDelete.value) return
  isDeleting.value = true
  try {
    await egressAxios.delete(`/pipelines/${pipelineToDelete.value.id}`)
    showSnackbar('Pipeline excluído com sucesso')
    await fetchPipelines()
  } catch (err) {
    showSnackbar('Erro ao excluir pipeline', 'error')
  } finally {
    isDeleting.value = false
    pipelineDeleteDialog.value = false
    pipelineToDelete.value = null
  }
}


// --- Global ---
const refreshData = () => {
  checkHealth()
  if (currentTab.value === 'results') {
    fetchResults()
  } else if (currentTab.value === 'pipelines') {
    fetchPipelines()
  }
}

onMounted(() => {
  checkHealth()
  fetchResults()
  fetchPipelines()
})
</script>

<template>
  <div class="egress-container">
    <!-- Header -->
    <div class="d-flex align-center mb-6">
      <v-avatar color="deep-orange" variant="tonal" rounded size="48" class="mr-4">
        <v-icon icon="mdi-logout-variant" size="24"></v-icon>
      </v-avatar>
      <div>
        <h2 class="text-h4 font-weight-bold">Saída (Egress)</h2>
        <div class="text-subtitle-1 text-medium-emphasis">
          Gerencie pipelines de saída e monitore resultados
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
      <v-btn color="deep-orange" variant="tonal" prepend-icon="mdi-refresh" @click="refreshData">
        Atualizar
      </v-btn>
    </div>

    <!-- Tabs -->
    <v-tabs v-model="currentTab" color="deep-orange" align-tabs="start" class="mb-4 bg-transparent">
      <v-tab value="results">Resultados</v-tab>
      <v-tab value="pipelines">Pipelines de Egress</v-tab>
    </v-tabs>

    <v-window v-model="currentTab" :touch="false" class="bg-transparent">
      <!-- Aba: Resultados -->
      <v-window-item value="results">
        <!-- Stats Resultados -->
        <v-row class="mb-6">
          <v-col cols="12" md="3">
            <v-card class="glass-card" variant="flat">
              <v-card-text>
                <div class="text-overline mb-1">TOTAL RESULTADOS</div>
                <div class="text-h4 font-weight-bold">{{ totalResults }}</div>
              </v-card-text>
            </v-card>
          </v-col>
          <v-col cols="12" md="3">
            <v-card class="glass-card" variant="flat">
              <v-card-text>
                <div class="text-overline mb-1">ENVIADOS</div>
                <div class="text-h4 font-weight-bold text-success">{{ sentCount }}</div>
              </v-card-text>
            </v-card>
          </v-col>
          <v-col cols="12" md="3">
            <v-card class="glass-card" variant="flat">
              <v-card-text>
                <div class="text-overline mb-1">FALHAS</div>
                <div class="text-h4 font-weight-bold text-error">{{ failedCount }}</div>
              </v-card-text>
            </v-card>
          </v-col>
          <v-col cols="12" md="3">
            <v-card class="glass-card" variant="flat">
              <v-card-text>
                <div class="text-overline mb-1">PENDENTES</div>
                <div class="text-h4 font-weight-bold text-warning">{{ pendingCount }}</div>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>

        <!-- Filter Resultados -->
        <v-card class="glass-card mb-4" variant="flat">
          <v-card-text class="d-flex align-center gap-4">
            <v-select
              v-model="statusFilter"
              :items="statusOptions"
              item-title="title"
              item-value="value"
              label="Filtrar por Status"
              variant="outlined"
              density="compact"
              hide-details
              clearable
              style="max-width: 250px"
              @update:model-value="fetchResults"
            ></v-select>
            <v-spacer></v-spacer>
            <v-btn variant="tonal" color="primary" prepend-icon="mdi-refresh" size="small" @click="fetchResults">
              Recarregar
            </v-btn>
          </v-card-text>
        </v-card>

        <!-- Table Resultados -->
        <v-card class="glass-card" variant="flat">
          <v-data-table
            :headers="resultHeaders"
            :items="results"
            :loading="loading"
            hover
          >
            <template #item.job_id="{ item }">
              <span class="text-caption font-weight-medium" style="font-family: monospace;">
                {{ item.job_id?.substring(0, 16) }}...
              </span>
            </template>

            <template #item.status="{ item }">
              <v-chip :color="statusColor(item.status)" size="small" variant="tonal">
                <v-icon start size="14">{{ statusIcon(item.status) }}</v-icon>
                {{ item.status }}
              </v-chip>
            </template>

            <template #item.attempts="{ item }">
              <v-chip size="x-small" variant="outlined">{{ item.attempts }}x</v-chip>
            </template>

            <template #item.last_error="{ item }">
              <span v-if="item.last_error" class="text-caption text-error" style="max-width: 250px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {{ item.last_error }}
              </span>
              <span v-else class="text-caption text-medium-emphasis">—</span>
            </template>

            <template #item.actions="{ item }">
              <v-btn icon variant="text" size="small" color="primary" @click="viewResultDetail(item)">
                <v-icon icon="mdi-eye-outline"></v-icon>
                <v-tooltip activator="parent" location="top">Detalhes</v-tooltip>
              </v-btn>
            </template>

            <template #no-data>
              <div class="text-center py-8">
                <v-icon icon="mdi-inbox-outline" size="48" color="grey" class="mb-2"></v-icon>
                <p class="text-medium-emphasis">Nenhum resultado encontrado</p>
              </div>
            </template>
          </v-data-table>
        </v-card>
      </v-window-item>

      <!-- Aba: Pipelines -->
      <v-window-item value="pipelines">
        <!-- Stats Pipelines -->
        <v-row class="mb-6">
          <v-col cols="12" md="4">
            <v-card class="glass-card" variant="flat">
              <v-card-text>
                <div class="text-overline mb-1">TOTAL PIPELINES</div>
                <div class="text-h4 font-weight-bold">{{ totalPipelines }}</div>
              </v-card-text>
            </v-card>
          </v-col>
          <v-col cols="12" md="4">
            <v-card class="glass-card" variant="flat">
              <v-card-text>
                <div class="text-overline mb-1">ATIVOS</div>
                <div class="text-h4 font-weight-bold text-success">{{ activePipelinesCount }}</div>
              </v-card-text>
            </v-card>
          </v-col>
          <v-col cols="12" md="4" class="d-flex align-center justify-end">
            <v-btn color="deep-orange" prepend-icon="mdi-plus" size="large" @click="openCreatePipeline">
              Novo Pipeline
            </v-btn>
          </v-col>
        </v-row>

        <!-- Table Pipelines -->
        <v-card class="glass-card" variant="flat">
          <v-data-table
            :headers="pipelineHeaders"
            :items="pipelines"
            :loading="loading"
            hover
          >
            <template #item.path="{ item }">
              <v-chip variant="outlined" color="deep-orange" size="small">
                {{ item.path }}
              </v-chip>
            </template>

            <template #item.output_url="{ item }">
              <span class="text-caption" style="max-width: 250px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {{ item.output_url }}
              </span>
            </template>

            <template #item.output_method="{ item }">
              <v-chip :color="item.output_method === 'POST' ? 'success' : 'warning'" size="x-small" variant="tonal">
                {{ item.output_method }}
              </v-chip>
            </template>

            <template #item.is_active="{ item }">
              <v-chip :color="item.is_active ? 'success' : 'grey'" size="x-small" variant="tonal">
                {{ item.is_active ? 'Ativo' : 'Inativo' }}
              </v-chip>
            </template>

            <template #item.actions="{ item }">
              <div class="d-flex justify-end gap-2">
                <v-btn icon variant="text" size="small" color="primary" @click="openEditPipeline(item)">
                  <v-icon icon="mdi-pencil-outline"></v-icon>
                  <v-tooltip activator="parent" location="top">Editar</v-tooltip>
                </v-btn>
                <v-btn icon variant="text" size="small" color="error" @click="confirmDeletePipeline(item)">
                  <v-icon icon="mdi-trash-can-outline"></v-icon>
                  <v-tooltip activator="parent" location="top">Excluir</v-tooltip>
                </v-btn>
              </div>
            </template>

            <template #no-data>
              <div class="text-center py-8">
                <v-icon icon="mdi-pipe-disconnected" size="48" color="grey" class="mb-2"></v-icon>
                <p class="text-medium-emphasis">Nenhum pipeline de egress configurado</p>
              </div>
            </template>
          </v-data-table>
        </v-card>
      </v-window-item>
    </v-window>

    <!-- Dialog Detalhes do Resultado -->
    <v-dialog v-model="detailDialog" max-width="700">
      <v-card class="glass-card">
        <v-card-title class="d-flex align-center pa-6 pb-4">
          <v-icon icon="mdi-information-outline" class="mr-2" color="primary"></v-icon>
          <span class="text-h5 font-weight-bold">Detalhes do Resultado</span>
          <v-spacer></v-spacer>
          <v-btn icon="mdi-close" variant="text" @click="detailDialog = false"></v-btn>
        </v-card-title>
        <v-card-text class="px-6 py-2" v-if="selectedResult">
          <v-row>
            <v-col cols="12" md="6">
              <div class="text-overline">Job ID</div>
              <div class="text-body-2 font-weight-medium" style="font-family: monospace; word-break: break-all;">{{ selectedResult.job_id }}</div>
            </v-col>
            <v-col cols="12" md="3">
              <div class="text-overline">Status</div>
              <v-chip :color="statusColor(selectedResult.status)" size="small" variant="tonal">
                <v-icon start size="14">{{ statusIcon(selectedResult.status) }}</v-icon>
                {{ selectedResult.status }}
              </v-chip>
            </v-col>
            <v-col cols="12" md="3">
              <div class="text-overline">Tentativas</div>
              <div class="text-body-2 font-weight-bold">{{ selectedResult.attempts }}</div>
            </v-col>
          </v-row>

          <v-divider class="my-4"></v-divider>

          <div v-if="selectedResult.last_error">
            <div class="text-overline mb-1">Último Erro</div>
            <v-alert type="error" variant="tonal" density="compact" class="mb-3">
              {{ selectedResult.last_error }}
            </v-alert>
          </div>

          <v-row v-if="selectedResult.created_at || selectedResult.updated_at || selectedResult.sent_at">
            <v-col cols="12" md="4" v-if="selectedResult.created_at">
              <div class="text-overline">Criado em</div>
              <div class="text-caption">{{ new Date(selectedResult.created_at).toLocaleString('pt-BR') }}</div>
            </v-col>
            <v-col cols="12" md="4" v-if="selectedResult.updated_at">
              <div class="text-overline">Atualizado em</div>
              <div class="text-caption">{{ new Date(selectedResult.updated_at).toLocaleString('pt-BR') }}</div>
            </v-col>
            <v-col cols="12" md="4" v-if="selectedResult.sent_at">
              <div class="text-overline">Enviado em</div>
              <div class="text-caption">{{ new Date(selectedResult.sent_at).toLocaleString('pt-BR') }}</div>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- Dialog Create/Edit Pipeline -->
    <v-dialog v-model="pipelineDialog" max-width="800" persistent>
      <v-card class="glass-card">
        <v-card-title class="d-flex align-center pa-6 pb-4">
          <span class="text-h5 font-weight-bold">{{ isEditingPipeline ? 'Editar' : 'Novo' }} Egress Pipeline</span>
          <v-spacer></v-spacer>
          <v-btn icon="mdi-close" variant="text" @click="closePipelineDialog"></v-btn>
        </v-card-title>

        <v-card-text class="px-6 py-2">
          <v-form @submit.prevent="savePipeline" id="egress-pipeline-form">
            <!-- Basic Info -->
            <div class="text-subtitle-1 font-weight-bold mb-3">Informações Básicas</div>
            <v-row>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="editedPipelineItem.name"
                  label="Nome do Pipeline"
                  variant="outlined"
                  required
                ></v-text-field>
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="editedPipelineItem.path"
                  label="Identificador (Path)"
                  variant="outlined"
                  hint="O ID ou Slug que o worker usará como pipeline_path"
                  persistent-hint
                  required
                ></v-text-field>
              </v-col>
            </v-row>
            <v-row>
              <v-col cols="12">
                <v-textarea
                  v-model="editedPipelineItem.description"
                  label="Descrição (Opcional)"
                  variant="outlined"
                  rows="2"
                  auto-grow
                ></v-textarea>
              </v-col>
            </v-row>

            <v-divider class="my-4"></v-divider>

            <!-- Output Destination -->
            <div class="text-subtitle-1 font-weight-bold mb-3">Destino do Callback (Output)</div>
            <v-row>
              <v-col cols="12" md="8">
                <v-text-field
                  v-model="editedPipelineItem.output_url"
                  label="URL do Webhook de Destino"
                  variant="outlined"
                  required
                ></v-text-field>
              </v-col>
              <v-col cols="12" md="4">
                <v-select
                  v-model="editedPipelineItem.output_method"
                  :items="['POST', 'PUT', 'PATCH']"
                  label="Método HTTP"
                  variant="outlined"
                ></v-select>
              </v-col>
            </v-row>

            <v-divider class="my-4"></v-divider>

            <!-- Retry Config -->
            <div class="text-subtitle-1 font-weight-bold mb-3">Configuração de Retentativas</div>
            <v-row>
              <v-col cols="12" md="4">
                <v-text-field
                  v-model.number="editedPipelineItem.retry_config.maxRetries"
                  type="number"
                  label="Máximo de Tentativas"
                  variant="outlined"
                  min="0"
                ></v-text-field>
              </v-col>
            </v-row>

            <v-row>
              <v-col cols="12">
                <v-switch
                  v-model="editedPipelineItem.is_active"
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
          <v-btn variant="text" @click="closePipelineDialog" :disabled="isSaving">Cancelar</v-btn>
          <v-btn
            color="deep-orange"
            variant="flat"
            type="submit"
            form="egress-pipeline-form"
            :loading="isSaving"
            class="px-6"
          >
            Salvar
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete Pipeline Dialog -->
    <v-dialog v-model="pipelineDeleteDialog" max-width="500">
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
          <v-btn variant="text" @click="pipelineDeleteDialog = false" :disabled="isDeleting">Cancelar</v-btn>
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

    <!-- Snackbar Geral -->
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
.egress-container {
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
.gap-4 {
  gap: 16px;
}
</style>
